from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    images: list[str] = []


class SessionCreateRequest(BaseModel):
    title: str | None = None


class SessionItem(BaseModel):
    id: str
    title: str
    updated_at: str


class UserSettings(BaseModel):
    default_model: str = "qwen3.5-plus"
    keep_history: bool = True
    language: str = "zh-CN"


class ModelInfo(BaseModel):
    id: str
    name: str
    capabilities: list[str]
    is_default: bool = False
