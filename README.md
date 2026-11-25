# LLM Chatbot with Key Failover and Response Caching

React + FastAPI + LiteLLM + SQLite. Multi-turn chat with a key pool that fails over automatically, a LiteLLM response cache, and per-request metadata (source, model, latency, tokens) shown next to every reply.

## 1. Live URLs

- Frontend: `TODO: https://<your-frontend>.vercel.app`
- Backend: `TODO: https://<your-backend>.onrender.com` (try `/health`)
- Repo: `TODO: https://github.com/<you>/<repo>`

## 2. Run locally

**With Docker** (needs a real key pool in `.env`):

```bash
cp .env.example .env     # set LLM_API_KEYS=keyA,keyB
make up                  # frontend :3000, backend :8000
make down
```

**Without Docker**

```bash
cd backend && pip install -r requirements.txt
export LLM_API_KEYS=keyA,keyB DATABASE_URL=sqlite:///./app.db ENABLE_FAILURE_SIMULATION=true
uvicorn app.main:app --port 8000
# new terminal
cd frontend && npm install && VITE_API_URL=http://localhost:8000 npm run dev
```

Tests (offline, uses LiteLLM `mock_response`): `make test` or `cd backend && pytest`.

**Deploying:** backend on Render/Railway/Fly from `/backend` (Dockerfile honors `$PORT`; attach a disk at `/data`). Set `LLM_API_KEYS`, `DATABASE_URL=sqlite:////data/app.db`, `ALLOWED_ORIGINS=<frontend url>`, `ENABLE_FAILURE_SIMULATION=true`. Frontend on Vercel/Netlify from `/frontend` with `VITE_API_URL=<backend url>` (build command `npm run build`, output `dist`).

## 3. Design decisions

- **Key fallback:** `LLM_API_KEYS` is split into `key_1..key_n`. For each request the gateway calls `litellm.completion` with the first key; any failure (429, quota, 5xx, timeout, auth) moves to the next key. `fallback_attempts` counts failed keys. If all fail, the API returns `503 {"detail":"all providers unavailable"}` and nothing is stored. Keys are never returned, only ids.
- **Caching:** LiteLLM's built-in `Cache` (in-memory by default, `CACHE_TYPE=disk` to persist). LiteLLM's key covers model + the full message list (system + history + new message), and excludes the API key, so a cache hit works whichever key would have served it. Hits are detected via `_hidden_params["cache_hit"]`, report the stored usage, `key_id: null`, `fallback_attempts: 0`.
- **SQLite sessions:** `messages` table as specified plus a `sessions` table holding the per-session system prompt and an index on `(session_id, id)`. WAL mode. The user and assistant rows are written in one transaction only after a successful answer, so 422/503 never touch history. The DB lives at `DATABASE_URL` (`/data/app.db` on a named volume).
- **Validation/errors:** Pydantic enforces 1-128 char session id and 1-4000 char trimmed message; all errors are JSON, unhandled exceptions return a generic JSON 500 with no stack trace.
- **Trade-off:** when `X-Simulate-Failure` is present the cache is bypassed, so failover is always demonstrable on a live call.

## 4. Verification

```bash
B=https://<backend>
# cache: same first message in two new sessions
curl -s $B/chat -H 'content-type: application/json' -d '{"session_id":"a1","message":"What is the capital of France?"}'   # LIVE_INFERENCE
curl -s $B/chat -H 'content-type: application/json' -d '{"session_id":"a2","message":"What is the capital of France?"}'   # LLM_CACHE, key_id null
# failover
curl -s $B/chat -H 'content-type: application/json' -H 'X-Simulate-Failure: key_1=429' -d '{"session_id":"a3","message":"Tell me a joke"}'   # key_id key_2, fallback_attempts 1
curl -s -i $B/chat -H 'content-type: application/json' -H 'X-Simulate-Failure: *=429' -d '{"session_id":"a4","message":"Tell me a joke"}'    # 503
curl -s $B/sessions/a1/messages
curl -s $B/health
```

In the UI: open "Session settings", type `key_1=429` in the simulate field and send; the Key line shows `key_2 (after 1 failed)`. Repeating a first message in a fresh page load shows `LLM_CACHE` with a lower latency. Each reply's input/output tokens are for that request only.

## 5. Setup used

- Editor: `TODO`
- AI tools: Claude (code generation and review), LiteLLM docs.

## 6. Bonus features

- System prompt field per session (stored server-side, part of the cache key).
- In-UI failure simulation field for demos.
- Optional disk cache (`CACHE_TYPE=disk`) so cache survives restarts.
