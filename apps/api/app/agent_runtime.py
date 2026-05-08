import json
from typing import Annotated, Any, AsyncGenerator, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI

from .config import settings
from .model_gateway import resolve_model
from .schemas import ChatRequest
from .web_search import run_web_search_tool


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _document_context_prefix(documents: list[Any]) -> str:
    if not documents:
        return ""

    blocks: list[str] = []
    for index, document in enumerate(documents, start=1):
        name = document.name if hasattr(document, "name") else document.get("name", f"文档{index}")
        kind = document.kind if hasattr(document, "kind") else document.get("kind", "text")
        content = document.content if hasattr(document, "content") else document.get("content", "")
        blocks.append(f"[{index}] {name} ({kind})\n{content}")

    context = "\n\n".join(blocks)
    return (
        "你将收到用户上传的文档解析内容。回答问题时，请优先依据文档内容作答；"
        "如果文档信息不足，再明确指出缺口并给出下一步建议。\n\n"
        f"【文档上下文】\n{context}\n\n"
    )


def _to_langchain_messages(payload: ChatRequest) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if settings.system_prompt_enabled and settings.system_prompt_template.strip():
        system_prompt = (
            f"{settings.system_prompt_template.strip()}\n\n"
            "你是一个基于工具的智能体。请优先直接回答；只有在涉及最新信息、实时数据、新闻公告、"
            "价格股价、天气、官网变更、比赛结果等明显需要外部事实核验的问题时，才调用 web_search 工具。\n"
            "同一轮回答最多调用 web_search 两次；如果第一次检索已经得到可用来源，就直接整理答案。"
            "如果连续两次检索仍无法获得足够事实，请明确说明不确定性，并停止继续搜索。\n"
            "如果使用了 web_search 返回的来源，最终答案必须附上“参考资料”小节，并使用 Markdown 链接。"
        )
        messages.append(SystemMessage(content=system_prompt))

    for index, item in enumerate(payload.messages):
        item_images = list(item.images)
        item_documents = list(item.documents)
        content_text = f"{_document_context_prefix(item_documents)}{item.content}".strip()
        is_last_user = index == len(payload.messages) - 1 and item.role == "user"
        if is_last_user and payload.images and not item_images:
            item_images = [{"name": f"image-{img_index + 1}", "data_url": image} for img_index, image in enumerate(payload.images)]

        if item.role == "user":
            if item_images:
                content_blocks: list[dict[str, Any]] = [{"type": "text", "text": content_text}]
                for image in item_images:
                    url = image.data_url if hasattr(image, "data_url") else image["data_url"]
                    content_blocks.append({"type": "image_url", "image_url": {"url": url}})
                messages.append(HumanMessage(content=content_blocks))
            else:
                messages.append(HumanMessage(content=content_text))
            continue

        message_cls = {"assistant": "assistant", "system": "system"}.get(item.role, item.role)
        if message_cls == "assistant":
            from langchain_core.messages import AIMessage

            messages.append(AIMessage(content=item.content))
        else:
            messages.append(SystemMessage(content=item.content))

    return messages


def _extract_text_segments(chunk: Any) -> list[str]:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return [content] if content else []
    if isinstance(content, list):
        parts: list[str] = []
        for segment in content:
            if isinstance(segment, str) and segment:
                parts.append(segment)
                continue
            if isinstance(segment, dict):
                text = segment.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return parts
    return []


def _extract_reasoning_segments(chunk: Any) -> list[str]:
    additional = getattr(chunk, "additional_kwargs", {}) or {}
    reasoning = additional.get("reasoning_content")
    if isinstance(reasoning, str):
        return [reasoning] if reasoning else []
    if isinstance(reasoning, list):
        parts: list[str] = []
        for segment in reasoning:
            if isinstance(segment, dict):
                text = segment.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return parts
    return []


def _stringify_tool_payload(value: Any) -> str:
    if value is None:
        return ""
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except TypeError:
        return str(value)


def _build_model(model: str, enable_thinking: bool) -> ChatOpenAI:
    extra_body: dict[str, Any] = {}
    if enable_thinking:
        extra_body["enable_thinking"] = True
    return ChatOpenAI(
        model=model,
        api_key=settings.model_api_key,
        base_url=settings.model_base_url.rstrip("/"),
        streaming=True,
        timeout=120,
        max_retries=1,
        extra_body=extra_body or None,
    )


def _build_agent_graph(model: str, enable_thinking: bool):
    @tool
    async def web_search(query: str, recency: str | None = None) -> str:
        """Search the web for fresh or externally verifiable information."""
        return await run_web_search_tool(query=query, recency=recency)

    tools = [web_search]
    llm = _build_model(model, enable_thinking).bind_tools(tools)

    async def agent_node(state: AgentState) -> dict[str, list[Any]]:
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile()


async def stream_agent_completion(payload: ChatRequest) -> AsyncGenerator[dict[str, Any], None]:
    has_images = len(payload.images) > 0 or any(message.images for message in payload.messages)
    selected_model = resolve_model(payload.model, has_images=has_images)
    thinking_enabled = settings.model_enable_thinking if payload.enable_thinking is None else payload.enable_thinking

    if not settings.model_api_key.strip():
        yield {"type": "content", "text": "未检测到 MODEL_API_KEY，请先在环境变量中配置后再试。"}
        return

    agent = _build_agent_graph(selected_model, thinking_enabled)
    recursion_limit = max(4, settings.agent_max_iterations * 2 + 1)
    initial_state = {"messages": _to_langchain_messages(payload)}

    try:
        async for event in agent.astream_events(
            initial_state,
            version="v2",
            config={"recursion_limit": recursion_limit},
        ):
            event_name = event.get("event", "")
            event_data = event.get("data", {}) or {}
            event_meta = event.get("metadata", {}) or {}

            if event_name == "on_tool_start" and settings.agent_tool_status_enabled:
                tool_input = event_data.get("input", {})
                query = tool_input.get("query", "") if isinstance(tool_input, dict) else ""
                tool_name = event.get("name", "tool")
                yield {
                    "type": "tool_start",
                    "text": query or tool_name,
                    "tool_call_id": str(event.get("run_id", "")),
                    "name": tool_name,
                    "input": _stringify_tool_payload(tool_input),
                }
                continue

            if event_name == "on_tool_end" and settings.agent_tool_status_enabled:
                tool_name = event.get("name", "tool")
                yield {
                    "type": "tool_end",
                    "text": tool_name,
                    "tool_call_id": str(event.get("run_id", "")),
                    "name": tool_name,
                    "output": _stringify_tool_payload(event_data.get("output")),
                }
                continue

            if event_name != "on_chat_model_stream":
                continue

            if event_meta.get("langgraph_node") != "agent":
                continue

            chunk = event_data.get("chunk")
            if chunk is None:
                continue

            for text in _extract_reasoning_segments(chunk):
                yield {"type": "reasoning", "text": text}

            for text in _extract_text_segments(chunk):
                yield {"type": "content", "text": text}
    except GraphRecursionError:
        yield {"type": "reasoning", "text": "[agent] 已达到本轮工具调用上限，以下内容基于已获取结果结束本轮回答。\n"}
    except Exception as exc:  # noqa: BLE001
        yield {"type": "content", "text": f"Agent 运行异常：{exc}"}
