from pydantic import BaseModel, Field


class ChatImage(BaseModel):
    name: str
    data_url: str


class ChatDocument(BaseModel):
    name: str
    content: str
    kind: str = "text"


class ChatToolCall(BaseModel):
    id: str
    name: str
    input: str = ""
    output: str = ""
    status: str = "done"
    collapsed: bool = True


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str
    images: list[ChatImage] = []
    documents: list[ChatDocument] = []
    toolCalls: list[ChatToolCall] = []


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    images: list[str] = []
    session_id: str | None = None
    enable_thinking: bool | None = None


class RegenerateRequest(BaseModel):
    model: str
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


class ModelApiKeyStatus(BaseModel):
    configured: bool


class ModelApiKeyUpdate(BaseModel):
    api_key: str


class AppConfig(BaseModel):
    model_base_url: str
    model_default: str
    model_vision_default: str
    model_configs: str
    model_enable_thinking: bool
    model_api_key_configured: bool
    web_search_enabled: bool
    web_search_auto_mode: str
    web_search_top_k: int
    web_search_fetch_top_k: int
    web_search_rerank_top_n: int
    web_search_query_planner_model: str
    baidu_search_api_url: str
    baidu_search_source: str
    baidu_search_api_key_configured: bool
    rerank_api_url: str
    rerank_model: str
    agent_max_iterations: int
    agent_tool_status_enabled: bool


class AppConfigUpdate(BaseModel):
    model_base_url: str
    model_api_key: str | None = None
    model_default: str
    model_vision_default: str
    model_configs: str
    model_enable_thinking: bool
    web_search_enabled: bool
    web_search_auto_mode: str
    web_search_top_k: int
    web_search_fetch_top_k: int
    web_search_rerank_top_n: int
    web_search_query_planner_model: str
    baidu_search_api_url: str
    baidu_search_api_key: str | None = None
    baidu_search_source: str
    rerank_api_url: str
    rerank_model: str
    agent_max_iterations: int
    agent_tool_status_enabled: bool


class UserSettings(BaseModel):
    default_model: str = "qwen3.5-plus"
    keep_history: bool = True
    language: str = "zh-CN"


class ModelInfo(BaseModel):
    id: str
    name: str
    capabilities: list[str]
    is_default: bool = False
