import asyncio
import json
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from .config import settings
from .schemas import ChatMessage


@dataclass
class WebSource:
    title: str
    url: str
    snippet: str
    cleaned: str = ""
    score: float = 0.0


@dataclass
class WebSearchOutcome:
    used: bool
    query: str = ""
    context: str = ""
    sources: list[WebSource] | None = None


def _last_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content.strip()
    return ""


def _heuristic_need_search(query: str) -> bool:
    if not query:
        return False
    hotwords = [
        "最新",
        "今天",
        "刚刚",
        "实时",
        "新闻",
        "近况",
        "现状",
        "官网",
        "价格",
        "发布",
        "公告",
        "比赛结果",
        "票房",
        "汇率",
        "股价",
        "天气",
    ]
    lowered = query.lower()
    if re.search(r"\b(202[4-9]|now|latest|today|news)\b", lowered):
        return True
    return any(word in query for word in hotwords)


def _safe_json_extract(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


async def _plan_search_query(messages: list[ChatMessage]) -> tuple[bool, str, str | None]:
    last_user = _last_user_message(messages)
    if not last_user:
        return False, "", None

    fallback = _heuristic_need_search(last_user)
    if not settings.model_api_key.strip():
        return fallback, last_user, None

    history = []
    for message in messages[-6:]:
        history.append(f"{message.role}: {message.content[:300]}")

    prompt = (
        "你是联网检索规划器。请判断该问题是否需要联网搜索最新信息。"
        "只返回JSON，不要输出其他内容。"
        "格式: {\"need_search\":true|false,\"query\":\"...\",\"recency\":\"week|month|year|null\"}."
        "query 需要简洁，便于搜索引擎检索。"
    )

    body = {
        "model": settings.web_search_query_planner_model,
        "stream": False,
        "enable_thinking": False,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "\n".join(history)},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.model_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.model_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        return fallback, last_user, None

    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    parsed = _safe_json_extract(content if isinstance(content, str) else "")

    need_search = parsed.get("need_search")
    query = parsed.get("query")
    recency = parsed.get("recency")

    decided = bool(need_search) if isinstance(need_search, bool) else fallback
    query_text = query.strip() if isinstance(query, str) and query.strip() else last_user
    recency_text = recency if recency in {"week", "month", "semiyear", "year"} else None
    return decided, query_text, recency_text


def _sanitize_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "iframe", "svg", "form", "header", "footer", "nav", "aside"]):
        tag.decompose()

    for node in soup.find_all(True):
        classes = " ".join(node.get("class", [])) if node.get("class") else ""
        ident = f"{node.get('id', '')} {classes}".lower()
        if any(key in ident for key in ["ad", "ads", "advert", "sponsor", "banner", "promo", "recommend"]):
            node.decompose()

    main = soup.find("article") or soup.find("main")
    root = main if main else soup
    texts: list[str] = []

    for element in root.find_all(["h1", "h2", "h3", "p", "li"]):
        text = " ".join(element.get_text(" ", strip=True).split())
        if len(text) >= 20:
            texts.append(text)
        if len("\n".join(texts)) > 5000:
            break

    if not texts:
        text = " ".join(root.get_text(" ", strip=True).split())
        return text[:5000]
    return "\n".join(texts)[:5000]


async def _fetch_one(client: httpx.AsyncClient, item: WebSource) -> WebSource:
    try:
        response = await client.get(item.url, follow_redirects=True)
        if response.status_code >= 400:
            return item
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return item
        item.cleaned = _sanitize_html_text(response.text)
    except Exception:
        return item
    return item


async def _baidu_search(query: str, recency: str | None) -> list[WebSource]:
    if not settings.baidu_search_api_key.strip():
        return []

    payload: dict = {
        "messages": [{"role": "user", "content": query}],
        "search_source": settings.baidu_search_source,
        "search_mode": "required",
        "stream": False,
        "resource_type_filter": [{"type": "web", "top_k": settings.web_search_top_k}],
        "enable_corner_markers": True,
    }
    if recency:
        payload["search_recency_filter"] = recency

    headers = {
        "X-Appbuilder-Authorization": f"Bearer {settings.baidu_search_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(settings.baidu_search_api_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    refs = data.get("references", [])
    items: list[WebSource] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("type") != "web":
            continue
        url = str(ref.get("url", "")).strip()
        title = str(ref.get("title", "")).strip()
        snippet = str(ref.get("snippet", "") or ref.get("content", "")).strip()
        if not url or not title:
            continue
        items.append(WebSource(title=title, url=url, snippet=snippet[:600]))
    return items


async def _rerank(query: str, items: list[WebSource]) -> list[WebSource]:
    if not items:
        return items
    if not settings.model_api_key.strip():
        return items

    docs = []
    for item in items:
        docs.append(f"标题: {item.title}\n摘要: {item.snippet}\n正文: {(item.cleaned or '')[:1200]}")

    payload = {
        "model": settings.rerank_model,
        "input": {"query": query, "documents": docs},
    }
    headers = {
        "Authorization": f"Bearer {settings.model_api_key}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "disable",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(settings.rerank_api_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return items

    results = data.get("output", {}).get("results", [])
    indexed = {idx: item for idx, item in enumerate(items)}
    ranked: list[WebSource] = []

    for row in results:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        score = row.get("relevance_score", 0)
        if not isinstance(idx, int) or idx not in indexed:
            continue
        item = indexed[idx]
        item.score = float(score)
        ranked.append(item)

    return ranked if ranked else items


def _build_web_context(query: str, items: list[WebSource]) -> str:
    lines = [
        "你可以使用以下联网检索参考信息回答问题。",
        "回答规则（必须遵守）：",
        "1) 只要使用了联网信息，就必须输出可点击的 Markdown 链接，格式为 [来源名](URL)。",
        "2) 禁止只输出 [来源1] 这种无链接占位符。",
        "3) 回答末尾必须追加“参考资料”小节，列出你实际使用过的来源链接。",
        "4) 若参考信息不足，请明确说明不确定，而不是编造。",
        f"检索词：{query}",
        "",
        "【联网参考】",
    ]

    for i, item in enumerate(items, start=1):
        excerpt = (item.cleaned or item.snippet or "").strip()
        excerpt = re.sub(r"\s+", " ", excerpt)
        excerpt = excerpt[:450]
        lines.append(f"[{i}] 标题: {item.title}")
        lines.append(f"[{i}] 链接: {item.url}")
        lines.append(f"[{i}] 摘录: {excerpt}")
        lines.append("")

    return "\n".join(lines).strip()


async def build_web_search_context(messages: list[ChatMessage]) -> WebSearchOutcome:
    if not settings.web_search_enabled:
        return WebSearchOutcome(used=False)

    need_search, query, recency = await _plan_search_query(messages)
    if settings.web_search_auto_mode == "disabled":
        need_search = False
    elif settings.web_search_auto_mode == "required":
        need_search = True

    if not need_search or not query:
        return WebSearchOutcome(used=False)

    items = await _baidu_search(query, recency)
    if not items:
        return WebSearchOutcome(used=False, query=query)

    fetch_top_k = max(1, min(settings.web_search_fetch_top_k, len(items)))
    async with httpx.AsyncClient(timeout=settings.web_search_fetch_timeout_sec) as client:
        fetched_items = await asyncio.gather(*[_fetch_one(client, item) for item in items[:fetch_top_k]])

    merged = fetched_items + items[fetch_top_k:]
    ranked = await _rerank(query, merged)
    top_n = max(1, min(settings.web_search_rerank_top_n, len(ranked)))
    final_items = ranked[:top_n]
    context = _build_web_context(query, final_items)
    return WebSearchOutcome(used=True, query=query, context=context, sources=final_items)
