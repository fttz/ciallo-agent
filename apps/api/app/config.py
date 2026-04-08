from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    app_name: str = "Ciallo Agent API"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 20
    parser_max_chars: int = 12000
    web_fetch_timeout_sec: int = 15
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_api_key: str = ""
    model_default: str = "qwen3.5-plus"
    model_vision_default: str = "qwen3.5-plus"
    model_configs: str = "qwen3.5-plus:Qwen3.5 Plus:text,vision"
    model_enable_thinking: bool = False
    web_search_enabled: bool = True
    web_search_auto_mode: str = "auto"
    web_search_top_k: int = 10
    web_search_fetch_top_k: int = 6
    web_search_rerank_top_n: int = 4
    web_search_fetch_timeout_sec: int = 8
    web_search_query_planner_model: str = "qwen3.5-plus"
    baidu_search_api_url: str = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
    baidu_search_api_key: str = ""
    baidu_search_source: str = "baidu_search_v2"
    rerank_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    rerank_model: str = "gte-rerank-v2"
    system_prompt_enabled: bool = True
    system_prompt_template: str = (
        "你的名字是 Ciallo Agent。\n"
        "请以朝武芳乃风格和用户自然交流，保持友好、真诚、乐于帮助。\n"
        "你喜欢并可在合适时机自然使用颜文字“Ciallo～(∠・ω< )⌒☆”，但无需频繁重复。"
    )
    session_store_path: str = "./data/sessions.json"

    model_config = SettingsConfigDict(env_file=(str(ROOT_ENV_PATH), ".env"), extra="ignore")


settings = Settings()
