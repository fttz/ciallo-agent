import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent_runtime import stream_agent_completion
from .config import ROOT_ENV_PATH, settings
from .file_parser import parse_uploaded_file, save_upload_file
from .model_gateway import list_models
from .schemas import AppConfig, AppConfigUpdate, ChatMessage, ChatRequest, ChatToolCall, ModelApiKeyStatus, ModelApiKeyUpdate, ParsedFile, RegenerateRequest, SessionCreateRequest, SessionItem, SessionUpdateRequest, UserSettings
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


def _env_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_env_values(values: dict[str, object]) -> None:
    ROOT_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ROOT_ENV_PATH.read_text(encoding="utf-8").splitlines() if ROOT_ENV_PATH.exists() else []
    remaining = set(values)
    updated_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in values:
            updated_lines.append(f"{key}={_env_value(values[key])}")
            remaining.discard(key)
        else:
            updated_lines.append(line)

    if remaining and updated_lines and updated_lines[-1].strip():
        updated_lines.append("")
    for key in values:
        if key in remaining:
            updated_lines.append(f"{key}={_env_value(values[key])}")

    ROOT_ENV_PATH.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


@app.get("/api/model-api-key/status")
def get_model_api_key_status() -> ModelApiKeyStatus:
    return ModelApiKeyStatus(configured=bool(settings.model_api_key.strip()))


@app.put("/api/model-api-key")
def update_model_api_key(payload: ModelApiKeyUpdate) -> ModelApiKeyStatus:
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    settings.model_api_key = api_key
    _write_env_values({"MODEL_API_KEY": api_key})
    return ModelApiKeyStatus(configured=True)


def _app_config() -> AppConfig:
    return AppConfig(
        model_base_url=settings.model_base_url,
        model_default=settings.model_default,
        model_vision_default=settings.model_vision_default,
        model_configs=settings.model_configs,
        model_enable_thinking=settings.model_enable_thinking,
        model_api_key_configured=bool(settings.model_api_key.strip()),
        web_search_enabled=settings.web_search_enabled,
        web_search_auto_mode=settings.web_search_auto_mode,
        web_search_top_k=settings.web_search_top_k,
        web_search_fetch_top_k=settings.web_search_fetch_top_k,
        web_search_rerank_top_n=settings.web_search_rerank_top_n,
        web_search_query_planner_model=settings.web_search_query_planner_model,
        baidu_search_api_url=settings.baidu_search_api_url,
        baidu_search_source=settings.baidu_search_source,
        baidu_search_api_key_configured=bool(settings.baidu_search_api_key.strip()),
        rerank_api_url=settings.rerank_api_url,
        rerank_model=settings.rerank_model,
        agent_max_iterations=settings.agent_max_iterations,
        agent_tool_status_enabled=settings.agent_tool_status_enabled,
    )


@app.get("/api/app-config")
def get_app_config() -> AppConfig:
    return _app_config()


@app.put("/api/app-config")
def update_app_config(payload: AppConfigUpdate) -> AppConfig:
    if payload.web_search_auto_mode not in {"auto", "required", "disabled"}:
        raise HTTPException(status_code=400, detail="web_search_auto_mode must be auto, required, or disabled")
    if payload.web_search_top_k < 1 or payload.web_search_fetch_top_k < 1 or payload.web_search_rerank_top_n < 1:
        raise HTTPException(status_code=400, detail="search limits must be greater than zero")
    if payload.agent_max_iterations < 1:
        raise HTTPException(status_code=400, detail="agent_max_iterations must be greater than zero")

    updates: dict[str, object] = {
        "MODEL_BASE_URL": payload.model_base_url.strip(),
        "MODEL_DEFAULT": payload.model_default.strip(),
        "MODEL_VISION_DEFAULT": payload.model_vision_default.strip(),
        "MODEL_CONFIGS": payload.model_configs.strip(),
        "MODEL_ENABLE_THINKING": payload.model_enable_thinking,
        "WEB_SEARCH_ENABLED": payload.web_search_enabled,
        "WEB_SEARCH_AUTO_MODE": payload.web_search_auto_mode,
        "WEB_SEARCH_TOP_K": payload.web_search_top_k,
        "WEB_SEARCH_FETCH_TOP_K": payload.web_search_fetch_top_k,
        "WEB_SEARCH_RERANK_TOP_N": payload.web_search_rerank_top_n,
        "WEB_SEARCH_QUERY_PLANNER_MODEL": payload.web_search_query_planner_model.strip(),
        "BAIDU_SEARCH_API_URL": payload.baidu_search_api_url.strip(),
        "BAIDU_SEARCH_SOURCE": payload.baidu_search_source.strip(),
        "RERANK_API_URL": payload.rerank_api_url.strip(),
        "RERANK_MODEL": payload.rerank_model.strip(),
        "AGENT_MAX_ITERATIONS": payload.agent_max_iterations,
        "AGENT_TOOL_STATUS_ENABLED": payload.agent_tool_status_enabled,
    }
    if payload.model_api_key and payload.model_api_key.strip():
        updates["MODEL_API_KEY"] = payload.model_api_key.strip()
    if payload.baidu_search_api_key and payload.baidu_search_api_key.strip():
        updates["BAIDU_SEARCH_API_KEY"] = payload.baidu_search_api_key.strip()

    settings.model_base_url = str(updates["MODEL_BASE_URL"])
    settings.model_default = str(updates["MODEL_DEFAULT"])
    settings.model_vision_default = str(updates["MODEL_VISION_DEFAULT"])
    settings.model_configs = str(updates["MODEL_CONFIGS"])
    settings.model_enable_thinking = bool(updates["MODEL_ENABLE_THINKING"])
    settings.web_search_enabled = bool(updates["WEB_SEARCH_ENABLED"])
    settings.web_search_auto_mode = str(updates["WEB_SEARCH_AUTO_MODE"])
    settings.web_search_top_k = int(updates["WEB_SEARCH_TOP_K"])
    settings.web_search_fetch_top_k = int(updates["WEB_SEARCH_FETCH_TOP_K"])
    settings.web_search_rerank_top_n = int(updates["WEB_SEARCH_RERANK_TOP_N"])
    settings.web_search_query_planner_model = str(updates["WEB_SEARCH_QUERY_PLANNER_MODEL"])
    settings.baidu_search_api_url = str(updates["BAIDU_SEARCH_API_URL"])
    settings.baidu_search_source = str(updates["BAIDU_SEARCH_SOURCE"])
    settings.rerank_api_url = str(updates["RERANK_API_URL"])
    settings.rerank_model = str(updates["RERANK_MODEL"])
    settings.agent_max_iterations = int(updates["AGENT_MAX_ITERATIONS"])
    settings.agent_tool_status_enabled = bool(updates["AGENT_TOOL_STATUS_ENABLED"])
    if "MODEL_API_KEY" in updates:
        settings.model_api_key = str(updates["MODEL_API_KEY"])
    if "BAIDU_SEARCH_API_KEY" in updates:
        settings.baidu_search_api_key = str(updates["BAIDU_SEARCH_API_KEY"])

    _write_env_values(updates)
    return _app_config()


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
