import sys
from pathlib import Path

import pytest


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


@pytest.fixture
def isolated_main(tmp_path, monkeypatch):
    from app import main
    from app.config import settings
    from app.session_store import SessionStore

    store = SessionStore(str(tmp_path / "sessions.json"))
    monkeypatch.setattr(main, "SESSION_STORE", store)
    main.ACTIVE_RUNS.clear()

    original_values = {
        "model_api_key": settings.model_api_key,
        "model_base_url": settings.model_base_url,
        "model_default": settings.model_default,
        "model_vision_default": settings.model_vision_default,
        "model_configs": settings.model_configs,
        "model_enable_thinking": settings.model_enable_thinking,
        "web_search_enabled": settings.web_search_enabled,
        "web_search_auto_mode": settings.web_search_auto_mode,
        "web_search_top_k": settings.web_search_top_k,
        "web_search_fetch_top_k": settings.web_search_fetch_top_k,
        "web_search_rerank_top_n": settings.web_search_rerank_top_n,
        "web_search_query_planner_model": settings.web_search_query_planner_model,
        "baidu_search_api_url": settings.baidu_search_api_url,
        "baidu_search_api_key": settings.baidu_search_api_key,
        "baidu_search_source": settings.baidu_search_source,
        "rerank_api_url": settings.rerank_api_url,
        "rerank_model": settings.rerank_model,
        "agent_max_iterations": settings.agent_max_iterations,
        "agent_tool_status_enabled": settings.agent_tool_status_enabled,
    }
    monkeypatch.setattr(main, "ROOT_ENV_PATH", tmp_path / ".env")
    yield main
    main.ACTIVE_RUNS.clear()
    for key, value in original_values.items():
        setattr(settings, key, value)
