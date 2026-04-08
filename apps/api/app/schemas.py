from pydantic import BaseModel, Field


class ChatImage(BaseModel):
    name: str
    data_url: str


class ChatDocument(BaseModel):
    name: str
    content: str
    kind: str = "text"


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str
    images: list[ChatImage] = []
    documents: list[ChatDocument] = []


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    images: list[str] = []
    session_id: str | None = None
    enable_thinking: bool | None = None


class SessionCreateRequest(BaseModel):
    title: str | None = None


class SessionUpdateRequest(BaseModel):
    title: str


class SessionItem(BaseModel):
    id: str
    title: str
    updated_at: str


class ParsedFile(BaseModel):
    filename: str
    size: int
    kind: str
    content: str


class UserSettings(BaseModel):
    default_model: str = "qwen3.5-plus"
    keep_history: bool = True
    language: str = "zh-CN"


class ModelInfo(BaseModel):
    id: str
    name: str
    capabilities: list[str]
    is_default: bool = False
