import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """All configuration comes from environment variables (read at call time)."""

    @property
    def api_keys(self) -> list[str]:
        return [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]

    @property
    def model(self) -> str:
        return os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")

    @property
    def database_path(self) -> str:
        url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
        # sqlite:////data/app.db -> /data/app.db ; sqlite:///./app.db -> ./app.db
        return url.replace("sqlite:///", "", 1) if url.startswith("sqlite:///") else url

    @property
    def allowed_origins(self) -> list[str]:
        raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    @property
    def simulation_enabled(self) -> bool:
        return _bool("ENABLE_FAILURE_SIMULATION", False)

    @property
    def cache_type(self) -> str:
        return os.getenv("CACHE_TYPE", "local")  # local (memory) | disk

    @property
    def cache_dir(self) -> str:
        return os.getenv("CACHE_DIR", "/data/llm_cache")

    @property
    def default_system_prompt(self) -> str:
        return os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise assistant.")

    @property
    def request_timeout(self) -> float:
        return float(os.getenv("LLM_TIMEOUT", "30"))

    @property
    def mock_llm(self) -> bool:
        # Offline mode for tests/demos: LiteLLM returns a canned response (no network).
        return _bool("LLM_MOCK", False)


settings = Settings()
