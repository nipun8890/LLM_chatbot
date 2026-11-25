import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db, llm
from .config import settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    llm.init_cache()
    yield


app = FastAPI(title="LLM Chatbot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: str | None = Field(default=None, max_length=4000)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("system_prompt", mode="before")
    @classmethod
    def strip_prompt(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    errs = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse({"detail": errs}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logging.exception("unhandled error")
    return JSONResponse({"detail": "internal server error"}, status_code=500)


@app.get("/health")
def health():
    ok = db.db_ok() and len(settings.api_keys) > 0
    if not ok:
        return JSONResponse(
            {"status": "error", "keys_configured": len(settings.api_keys), "cache_enabled": llm.litellm.cache is not None},
            status_code=503,
        )
    return {"status": "ok", "keys_configured": len(settings.api_keys), "cache_enabled": llm.litellm.cache is not None}


@app.post("/chat")
def chat(req: ChatRequest, x_simulate_failure: str | None = Header(default=None)):
    system_prompt = req.system_prompt or db.get_system_prompt(req.session_id) or settings.default_system_prompt
    history = [{"role": m["role"], "content": m["content"]} for m in db.get_history(req.session_id)]
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": req.message}]

    key_ids = [f"key_{i}" for i in range(1, len(settings.api_keys) + 1)]
    simulate = llm.parse_simulation(x_simulate_failure, key_ids)

    try:
        result = llm.complete(messages, simulate)
    except llm.AllProvidersUnavailable:
        return JSONResponse({"detail": "all providers unavailable"}, status_code=503)

    db.save_exchange(req.session_id, req.system_prompt, req.message, result["reply"], result["metadata"])
    return {"session_id": req.session_id, "reply": result["reply"], "metadata": result["metadata"]}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    msgs = db.get_history(session_id)
    if not msgs:
        return JSONResponse({"detail": "session not found"}, status_code=404)
    return {"session_id": session_id, "messages": msgs}
