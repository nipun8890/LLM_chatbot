import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.update(
    LLM_API_KEYS="k1,k2",
    LLM_MOCK="true",
    ENABLE_FAILURE_SIMULATION="true",
    DATABASE_URL=f"sqlite:///{tempfile.mkdtemp()}/test.db",
)

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def chat(client, sid, msg, headers=None, **extra):
    return client.post("/chat", json={"session_id": sid, "message": msg, **extra}, headers=headers or {})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_live_then_cache_across_sessions(client):
    a = chat(client, "s-a", "What is the capital of France?").json()
    b = chat(client, "s-b", "What is the capital of France?").json()
    assert a["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert a["metadata"]["key_id"] == "key_1"
    assert b["metadata"]["resolution_source"] == "LLM_CACHE"
    assert b["metadata"]["key_id"] is None and b["metadata"]["fallback_attempts"] == 0
    assert a["reply"] == b["reply"]
    assert a["metadata"]["input_tokens"] == b["metadata"]["input_tokens"]
    assert isinstance(b["metadata"]["latency_ms"], int)


def test_different_message_not_cached(client):
    assert chat(client, "s-c", "Something totally different").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_multi_turn_and_history(client):
    chat(client, "s-h", "hello there")
    r = chat(client, "s-h", "second message").json()
    assert r["reply"]
    h = client.get("/sessions/s-h/messages").json()
    assert [m["role"] for m in h["messages"]] == ["user", "assistant", "user", "assistant"]
    assert "metadata" in h["messages"][1] and "metadata" not in h["messages"][0]
    assert client.get("/sessions/s-other/messages").json() == {"detail": "session not found"}


def test_failover(client):
    r = chat(client, "s-f1", "failover one", {"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200
    m = r.json()["metadata"]
    assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1 and m["resolution_source"] == "LIVE_INFERENCE"
    r = chat(client, "s-f2", "failover two", {"X-Simulate-Failure": "key_1=500"})
    assert r.json()["metadata"]["key_id"] == "key_2"


def test_all_fail_503_not_saved(client):
    r = chat(client, "s-503", "all fail", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert client.get("/sessions/s-503/messages").status_code == 404
    r = chat(client, "s-503b", "all fail", {"X-Simulate-Failure": "key_1=429,key_2=500"})
    assert r.status_code == 503


@pytest.mark.parametrize(
    "body",
    [
        {"session_id": "x"},
        {"message": "hi"},
        {"session_id": "", "message": "hi"},
        {"session_id": "x", "message": "   "},
        {"session_id": "x", "message": "a" * 4001},
        {"session_id": "x" * 129, "message": "hi"},
    ],
)
def test_validation_422(client, body):
    r = client.post("/chat", json=body)
    assert r.status_code == 422 and "detail" in r.json()


def test_malformed_json(client):
    r = client.post("/chat", content="{bad", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_system_prompt_changes_cache_key(client):
    a = chat(client, "s-sp1", "cache me please", system_prompt="You are a pirate.").json()
    b = chat(client, "s-sp2", "cache me please").json()
    assert b["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert a["session_id"] == "s-sp1"
