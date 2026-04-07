from typing import AsyncGenerator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .file_parser import parse_uploaded_file, save_upload_file
from .model_gateway import list_models, stream_chat_completion
from .schemas import ChatRequest, ParsedFile, SessionCreateRequest, SessionItem, SessionUpdateRequest, UserSettings
from .session_store import SessionStore

app = FastAPI(title=settings.app_name)

USER_SETTINGS = UserSettings()
SESSION_STORE = SessionStore(settings.session_store_path)

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


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    stored_history = SESSION_STORE.get_messages(payload.session_id) if payload.session_id else []
    merged_messages = [*stored_history, *payload.messages]
    request_payload = ChatRequest(model=payload.model, messages=merged_messages, images=payload.images)

    if payload.session_id and payload.messages:
        last_user = payload.messages[-1]
        if last_user.role == "user":
            SESSION_STORE.append_message(
                payload.session_id,
                "user",
                last_user.content,
                last_user.images,
                last_user.documents,
            )

    async def event_stream() -> AsyncGenerator[str, None]:
        assistant_parts: list[str] = []
        async for token in stream_chat_completion(request_payload):
            assistant_parts.append(token)
            yield f"data: {token}\n\n"

        if payload.session_id:
            assistant_text = "".join(assistant_parts).strip()
            if assistant_text:
                SESSION_STORE.append_message(payload.session_id, "assistant", assistant_text)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
