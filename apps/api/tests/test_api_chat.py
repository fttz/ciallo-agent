import asyncio
import json

from fastapi.testclient import TestClient

from app.schemas import ChatRequest


def _sse_payloads(raw_text: str) -> list[dict]:
    payloads: list[dict] = []
    for line in raw_text.splitlines():
        if not line.startswith("data: "):
            continue
        data = line.removeprefix("data: ").strip()
        if data == "[DONE]":
            continue
        payloads.append(json.loads(data))
    return payloads


def test_chat_stream_persists_user_assistant_and_tool_calls(isolated_main, monkeypatch):
    async def fake_stream(_payload):
        yield {
            "type": "tool_start",
            "text": "天津天气",
            "tool_call_id": "search-1",
            "name": "web_search",
            "input": "天津天气",
        }
        yield {
            "type": "tool_end",
            "text": "web_search",
            "tool_call_id": "search-1",
            "name": "web_search",
            "output": "晴转多云",
        }
        yield {"type": "content", "text": "今天"}
        yield {"type": "content", "text": "适合出门。"}

    monkeypatch.setattr(isolated_main, "stream_agent_completion", fake_stream)
    client = TestClient(isolated_main.app)
    session_id = client.post("/api/sessions", json={"title": "天气"}).json()["id"]

    response = client.post(
        "/api/chat/stream",
        json={
            "session_id": session_id,
            "model": "qwen3.5-plus",
            "messages": [{"role": "user", "content": "查一下天津天气"}],
            "images": [],
        },
    )

    assert response.status_code == 200
    payloads = _sse_payloads(response.text)
    assert [item["type"] for item in payloads] == ["tool_start", "tool_end", "content", "content"]

    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "查一下天津天气"
    assert messages[1]["content"] == "今天适合出门。"
    assert messages[1]["toolCalls"][0]["name"] == "web_search"
    assert messages[1]["toolCalls"][0]["output"] == "晴转多云"


def test_generation_finishes_and_saves_without_stream_consumer(isolated_main, monkeypatch):
    async def fake_stream(_payload):
        yield {"type": "content", "text": "后台"}
        await asyncio.sleep(0)
        yield {"type": "content", "text": "完成"}

    async def run_case():
        monkeypatch.setattr(isolated_main, "stream_agent_completion", fake_stream)
        session = isolated_main.SESSION_STORE.create_session("刷新恢复")
        payload = ChatRequest(
            session_id=session.id,
            model="qwen3.5-plus",
            messages=[{"role": "user", "content": "刷新页面后继续生成"}],
            images=[],
        )

        run = isolated_main._start_generation(session.id, payload)
        assert isolated_main.ACTIVE_RUNS[session.id] is run
        await run.task

        messages = isolated_main.SESSION_STORE.get_messages(session.id)
        assert messages[-1].role == "assistant"
        assert messages[-1].content == "后台完成"
        assert session.id not in isolated_main.ACTIVE_RUNS

    asyncio.run(run_case())


def test_cancel_active_run_stops_background_generation(isolated_main, monkeypatch):
    started = asyncio.Event()

    async def fake_stream(_payload):
        started.set()
        await asyncio.sleep(10)
        yield {"type": "content", "text": "不应保存"}

    async def run_case():
        monkeypatch.setattr(isolated_main, "stream_agent_completion", fake_stream)
        session = isolated_main.SESSION_STORE.create_session("停止生成")
        payload = ChatRequest(
            session_id=session.id,
            model="qwen3.5-plus",
            messages=[{"role": "user", "content": "请生成长回答"}],
            images=[],
        )

        run = isolated_main._start_generation(session.id, payload)
        await started.wait()
        assert isolated_main.get_active_run(session.id) == {"running": True}
        result = await isolated_main.cancel_active_run(session.id)
        assert result == {"cancelled": True}
        await asyncio.gather(run.task, return_exceptions=True)

        assert isolated_main.get_active_run(session.id) == {"running": False}
        assert isolated_main.SESSION_STORE.get_messages(session.id) == []

    asyncio.run(run_case())
