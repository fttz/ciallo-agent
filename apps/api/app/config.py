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
    session_store_path: str = "./data/sessions.json"

    model_config = SettingsConfigDict(env_file=(str(ROOT_ENV_PATH), ".env"), extra="ignore")


settings = Settings()
