"""LiteLLM gateway: key pool, ordered failover, built-in response cache."""
import logging
import time

import litellm
from litellm.caching.caching import Cache

from .config import settings

log = logging.getLogger("llm")
litellm.drop_params = True
litellm.suppress_debug_info = True

SIM_STATUSES = {429, 500, 502, 503}


class AllProvidersUnavailable(Exception):
    pass


def init_cache() -> None:
    if settings.cache_type == "disk":
        litellm.cache = Cache(type="disk", disk_cache_dir=settings.cache_dir)
    else:
        litellm.cache = Cache(type="local")


def parse_simulation(header: str | None, key_ids: list[str]) -> dict[str, int]:
    """'key_1=429,key_2=500' or '*=429' -> {key_id: status}."""
    out: dict[str, int] = {}
    if not header or not settings.simulation_enabled:
        return out
    for part in header.split(","):
        if "=" not in part:
            continue
        k, v = (s.strip() for s in part.split("=", 1))
        if not v.isdigit() or int(v) not in SIM_STATUSES:
            continue
        for kid in (key_ids if k == "*" else [k]):
            out[kid] = int(v)
    return out


def complete(messages: list[dict], simulate: dict[str, int] | None = None) -> dict:
    """Try each key in order. Returns reply + metadata. Raises AllProvidersUnavailable."""
    keys = settings.api_keys
    model = settings.model
    simulate = simulate or {}
    failures = 0
    start = time.perf_counter()

    for idx, key in enumerate(keys, start=1):
        key_id = f"key_{idx}"
        if key_id in simulate:
            # Injected failure for this request only; behaves like the provider returned that status.
            log.warning("simulated %s on %s", simulate[key_id], key_id)
            failures += 1
            continue
        try:
            kwargs = dict(model=model, messages=messages, api_key=key, timeout=settings.request_timeout, num_retries=0)
            # While simulating, bypass the cache so failover is always demonstrable on live calls.
            kwargs["caching"] = not simulate
            if settings.mock_llm:
                kwargs["mock_response"] = "Mock reply to: " + messages[-1]["content"][:200]
            resp = litellm.completion(**kwargs)
        except Exception as e:  # 429 / quota / 5xx / auth / network -> next key
            log.warning("%s failed: %s", key_id, type(e).__name__)
            failures += 1
            continue

        text = (resp.choices[0].message.content or "").strip()
        if not text:
            failures += 1
            continue
        hit = bool((getattr(resp, "_hidden_params", None) or {}).get("cache_hit"))
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        return {
            "reply": text,
            "metadata": {
                "resolution_source": "LLM_CACHE" if hit else "LIVE_INFERENCE",
                "model": model,
                "latency_ms": max(0, int((time.perf_counter() - start) * 1000)),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "key_id": None if hit else key_id,
                "fallback_attempts": 0 if hit else failures,
            },
        }
    raise AllProvidersUnavailable()
