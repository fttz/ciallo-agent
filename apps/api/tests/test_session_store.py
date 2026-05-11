from app.schemas import ChatDocument, ChatImage, ChatToolCall
from app.session_store import SessionStore


def test_session_store_persists_messages_with_attachments_and_tool_calls(tmp_path):
    store_path = tmp_path / "sessions.json"
    store = SessionStore(str(store_path))
    session = store.create_session()

    assert store.append_message(
        session.id,
        role="user",
        content="帮我查天气",
        images=[ChatImage(name="sky.png", data_url="data:image/png;base64,aaa")],
        documents=[ChatDocument(name="notes.md", content="hello", kind="text")],
    )
    assert store.append_message(
        session.id,
        role="assistant",
        content="今天适合带伞。",
        tool_calls=[
            ChatToolCall(
                id="tool-1",
                name="web_search",
                input="天津今日天气",
                output="有降雨概率",
                status="done",
                collapsed=True,
            )
        ],
    )

    reloaded = SessionStore(str(store_path))
    messages = reloaded.get_messages(session.id)

    assert len(messages) == 2
    assert messages[0].images[0].name == "sky.png"
    assert messages[0].documents[0].name == "notes.md"
    assert messages[1].toolCalls[0].name == "web_search"
    assert messages[1].toolCalls[0].output == "有降雨概率"


def test_session_store_updates_new_session_title_from_first_user_message(tmp_path):
    store = SessionStore(str(tmp_path / "sessions.json"))
    session = store.create_session()

    store.append_message(session.id, role="user", content="这是第一条用户消息，用来生成会话标题")
    sessions = store.list_sessions()

    assert sessions[0].title == "这是第一条用户消息，用来生成会话标题"[:24]
