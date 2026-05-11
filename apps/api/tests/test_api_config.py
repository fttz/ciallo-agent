from fastapi.testclient import TestClient

from app.config import settings


def _config_payload(**overrides):
    payload = {
        "model_base_url": "https://example.test/v1",
        "model_api_key": "",
        "model_default": "qwen-plus",
        "model_vision_default": "qwen-vl",
        "model_configs": "qwen-plus:Qwen Plus:text;qwen-vl:Qwen VL:text,vision",
        "model_enable_thinking": False,
        "web_search_enabled": True,
        "web_search_auto_mode": "auto",
        "web_search_top_k": 8,
        "web_search_fetch_top_k": 4,
        "web_search_rerank_top_n": 3,
        "web_search_query_planner_model": "qwen-plus",
        "baidu_search_api_url": "https://search.example.test",
        "baidu_search_api_key": "",
        "baidu_search_source": "baidu_search_v2",
        "rerank_api_url": "https://rerank.example.test",
        "rerank_model": "gte-rerank-v2",
        "agent_max_iterations": 3,
        "agent_tool_status_enabled": True,
    }
    payload.update(overrides)
    return payload


def test_app_config_updates_runtime_settings_and_env_file(isolated_main):
    client = TestClient(isolated_main.app)

    response = client.put(
        "/api/app-config",
        json=_config_payload(model_api_key="model-secret", baidu_search_api_key="search-secret"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["model_api_key_configured"] is True
    assert data["baidu_search_api_key_configured"] is True
    assert settings.model_base_url == "https://example.test/v1"
    assert settings.model_api_key == "model-secret"
    assert settings.web_search_rerank_top_n == 3

    env_text = isolated_main.ROOT_ENV_PATH.read_text(encoding="utf-8")
    assert "MODEL_API_KEY=model-secret" in env_text
    assert "BAIDU_SEARCH_API_KEY=search-secret" in env_text
    assert "WEB_SEARCH_RERANK_TOP_N=3" in env_text


def test_app_config_rejects_invalid_limits(isolated_main):
    client = TestClient(isolated_main.app)

    response = client.put("/api/app-config", json=_config_payload(web_search_top_k=0))

    assert response.status_code == 400
    assert "search limits" in response.json()["detail"]


def test_model_api_key_endpoint_writes_env_without_touching_real_env(isolated_main):
    client = TestClient(isolated_main.app)

    response = client.put("/api/model-api-key", json={"api_key": "sk-test"})

    assert response.status_code == 200
    assert response.json() == {"configured": True}
    assert settings.model_api_key == "sk-test"
    assert isolated_main.ROOT_ENV_PATH.read_text(encoding="utf-8") == "MODEL_API_KEY=sk-test\n"
