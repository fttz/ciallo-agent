from datetime import datetime, timezone
from uuid import uuid4
from typing import AsyncGenerator

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .file_parser import save_upload_file
from .model_gateway import list_models, stream_chat_completion
from .schemas import ChatRequest, SessionCreateRequest, SessionItem, UserSettings

app = FastAPI(title=settings.app_name)

SESSIONS: dict[str, dict] = {}
USER_SETTINGS = UserSettings()

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
    items = []
    for data in SESSIONS.values():
        items.append(
            SessionItem(
                id=data["id"],
                title=data["title"],
                updated_at=data["updated_at"],
            )
        )
    return sorted(items, key=lambda i: i.updated_at, reverse=True)


@app.post("/api/sessions")
def create_session(payload: SessionCreateRequest) -> SessionItem:
    session_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    title = payload.title or "新会话"
    SESSIONS[session_id] = {
        "id": session_id,
        "title": title,
        "updated_at": now,
        "messages": [],
    }
    return SessionItem(id=session_id, title=title, updated_at=now)


@app.get("/api/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    item = SESSIONS.get(session_id)
    if not item:
        return []
    return item["messages"]


@app.get("/api/settings")
def get_settings() -> UserSettings:
    return USER_SETTINGS


@app.put("/api/settings")
def update_settings(payload: UserSettings) -> UserSettings:
    global USER_SETTINGS
    USER_SETTINGS = payload
    return USER_SETTINGS


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        async for token in stream_chat_completion(payload):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/files/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    saved = []
    for file in files:
        saved.append(await save_upload_file(settings.upload_dir, file))

    return {"count": len(saved), "files": saved}
