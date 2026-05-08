import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent_runtime import stream_agent_completion
from .config import settings
from .file_parser import parse_uploaded_file, save_upload_file
from .model_gateway import list_models
from .schemas import ChatMessage, ChatRequest, ChatToolCall, ModelApiKeyStatus, ModelApiKeyUpdate, ParsedFile, RegenerateRequest, SessionCreateRequest, SessionItem, SessionUpdateRequest, UserSettings
from .session_store import SessionStore

app = FastAPI(title=settings.app_name)

USER_SETTINGS = UserSettings()
SESSION_STORE = SessionStore(settings.session_store_path)


@dataclass
class GenerationRun:
    session_id: str
    queue: asyncio.Queue[dict | None] = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None


ACTIVE_RUNS: dict[str, GenerationRun] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/models")
def models():
    return list_models()


@app.get("/api/sessions")
def list_sessions() -> list[SessionItem]:
    return SESSION_STORE.list_sessions()


@app.post("/api/sessions")
def create_session(payload: SessionCreateRequest) -> SessionItem:
    return SESSION_STORE.create_session(payload.title)


@app.get("/api/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    return SESSION_STORE.get_messages(session_id)


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, payload: SessionUpdateRequest) -> SessionItem:
    updated = SESSION_STORE.rename_session(session_id, payload.title)
    if not updated:
        raise HTTPException(status_code=404, detail="session not found")
    return updated


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    deleted = SESSION_STORE.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@app.get("/api/settings")
def get_settings() -> UserSettings:
    return USER_SETTINGS


@app.put("/api/settings")
def update_settings(payload: UserSettings) -> UserSettings:
    global USER_SETTINGS
    USER_SETTINGS = payload
    return USER_SETTINGS


@app.get("/api/model-api-key/status")
def get_model_api_key_status() -> ModelApiKeyStatus:
    return ModelApiKeyStatus(configured=bool(settings.model_api_key.strip()))


@app.put("/api/model-api-key")
def update_model_api_key(payload: ModelApiKeyUpdate) -> ModelApiKeyStatus:
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    settings.model_api_key = api_key
    return ModelApiKeyStatus(configured=True)


def _track_tool_call(chunk: dict, tool_call_order: list[str], tool_calls: dict[str, ChatToolCall]) -> None:
    token_type = chunk.get("type", "content")
    if token_type not in {"tool_start", "tool_end"}:
        return

    tool_call_id = str(chunk.get("tool_call_id") or f"tool-{len(tool_call_order) + 1}")
    if tool_call_id not in tool_calls:
        tool_call_order.append(tool_call_id)
        tool_calls[tool_call_id] = ChatToolCall(
            id=tool_call_id,
            name=str(chunk.get("name") or "tool"),
            input="",
            output="",
            status="running",
            collapsed=True,
        )

    current_tool = tool_calls[tool_call_id]
    if token_type == "tool_start":
        current_tool.name = str(chunk.get("name") or current_tool.name)
        current_tool.input = str(chunk.get("input") or current_tool.input)
        current_tool.status = "running"
    else:
        current_tool.name = str(chunk.get("name") or current_tool.name)
        current_tool.output = str(chunk.get("output") or current_tool.output)
        current_tool.status = "done"


async def _run_generation(session_id: str, request_payload: ChatRequest, run: GenerationRun) -> None:
    assistant_parts: list[str] = []
    tool_call_order: list[str] = []
    tool_calls: dict[str, ChatToolCall] = {}

    try:
        async for chunk in stream_agent_completion(request_payload):
            token = chunk.get("text", "")
            token_type = chunk.get("type", "content")
            if not token and token_type not in {"tool_start", "tool_end"}:
                continue
            if token_type == "content":
                assistant_parts.append(token)
            else:
                _track_tool_call(chunk, tool_call_order, tool_calls)
            await run.queue.put({**chunk, "token": token, "type": token_type})

        assistant_text = "".join(assistant_parts).strip()
        assistant_tool_calls = [tool_calls[tool_id] for tool_id in tool_call_order]
        if assistant_text or assistant_tool_calls:
            SESSION_STORE.append_message(session_id, "assistant", assistant_text, tool_calls=assistant_tool_calls)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        error_text = f"生成任务异常：{exc}"
        await run.queue.put({"type": "content", "text": error_text, "token": error_text})
        SESSION_STORE.append_message(session_id, "assistant", error_text)
    finally:
        await run.queue.put(None)
        if ACTIVE_RUNS.get(session_id) is run:
            ACTIVE_RUNS.pop(session_id, None)


def _start_generation(session_id: str, request_payload: ChatRequest) -> GenerationRun:
    existing = ACTIVE_RUNS.get(session_id)
    if existing and existing.task and not existing.task.done():
        existing.task.cancel()

    run = GenerationRun(session_id=session_id)
    run.task = asyncio.create_task(_run_generation(session_id, request_payload, run))
    run.task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
    ACTIVE_RUNS[session_id] = run
    return run


def _stream_run(run: GenerationRun) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        while True:
            chunk = await run.queue.get()
            if chunk is None:
                break
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    if not payload.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    stored_history = SESSION_STORE.get_messages(payload.session_id)
    merged_messages = [*stored_history, *payload.messages]

    request_payload = ChatRequest(
        model=payload.model,
        messages=merged_messages,
        images=payload.images,
        enable_thinking=payload.enable_thinking,
    )

    if payload.messages:
        last_user = payload.messages[-1]
        if last_user.role == "user":
            SESSION_STORE.append_message(
                payload.session_id,
                "user",
                last_user.content,
                last_user.images,
                last_user.documents,
            )

    return _stream_run(_start_generation(payload.session_id, request_payload))


@app.delete("/api/sessions/{session_id}/active-run")
async def cancel_active_run(session_id: str) -> dict:
    run = ACTIVE_RUNS.get(session_id)
    if run and run.task and not run.task.done():
        run.task.cancel()
        ACTIVE_RUNS.pop(session_id, None)
        await run.queue.put(None)
        return {"cancelled": True}
    return {"cancelled": False}


@app.get("/api/sessions/{session_id}/active-run")
def get_active_run(session_id: str) -> dict:
    run = ACTIVE_RUNS.get(session_id)
    running = bool(run and run.task and not run.task.done())
    return {"running": running}


@app.post("/api/sessions/{session_id}/regenerate")
async def regenerate_last_answer(session_id: str, payload: RegenerateRequest) -> StreamingResponse:
    SESSION_STORE.remove_trailing_assistant(session_id)
    stored_history = SESSION_STORE.get_messages(session_id)
    if not stored_history or stored_history[-1].role != "user":
        raise HTTPException(status_code=400, detail="no user message to regenerate")

    request_payload = ChatRequest(
        model=payload.model,
        messages=stored_history,
        enable_thinking=payload.enable_thinking,
    )

    return _stream_run(_start_generation(session_id, request_payload))


@app.post("/api/files/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    saved = []
    for file in files:
        saved.append(await save_upload_file(settings.upload_dir, file))

    return {"count": len(saved), "files": saved}


@app.post("/api/files/parse")
async def parse_files(files: list[UploadFile] = File(...)) -> dict:
    parsed: list[ParsedFile] = []
    for file in files:
        item = await parse_uploaded_file(
            settings.upload_dir,
            file,
            max_chars=settings.parser_max_chars,
            web_fetch_timeout_sec=settings.web_fetch_timeout_sec,
        )
        parsed.append(ParsedFile(**item))

    return {"count": len(parsed), "files": parsed}
