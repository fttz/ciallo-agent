import json
from typing import AsyncGenerator

import httpx

from .config import settings
from .schemas import ChatRequest, ModelInfo


def _parse_models_from_env() -> list[ModelInfo]:
    models: list[ModelInfo] = []
    # Format: model_id:display_name:cap1,cap2;model_id:display_name:cap1
    for item in settings.model_configs.split(";"):
        segment = item.strip()
        if not segment:
            continue
        parts = segment.split(":", 2)
        if len(parts) < 3:
            continue
        model_id, name, caps = parts
        capabilities = [cap.strip() for cap in caps.split(",") if cap.strip()]
        models.append(
            ModelInfo(
                id=model_id.strip(),
                name=name.strip(),
                capabilities=capabilities,
                is_default=model_id.strip() == settings.model_default,
            )
        )

    if not models:
        models = [
            ModelInfo(
                id=settings.model_default,
                name="Qwen3.5 Plus",
                capabilities=["text"],
                is_default=True,
            )
        ]
    return models


def list_models() -> list[ModelInfo]:
    return _parse_models_from_env()


def _find_model(model_id: str) -> ModelInfo | None:
    for item in _parse_models_from_env():
        if item.id == model_id:
            return item
    return None


def _first_vision_model() -> ModelInfo | None:
    for item in _parse_models_from_env():
        if "vision" in item.capabilities:
            return item
    return None


def resolve_model(requested_model: str, has_images: bool = False) -> str:
    available = {item.id for item in _parse_models_from_env()}
    selected = requested_model if requested_model in available else settings.model_default

    if not has_images:
        return selected

    selected_info = _find_model(selected)
    if selected_info and "vision" in selected_info.capabilities:
        return selected

    preferred_vision = _find_model(settings.model_vision_default)
    if preferred_vision and "vision" in preferred_vision.capabilities:
        return preferred_vision.id

    fallback_vision = _first_vision_model()
    if fallback_vision:
        return fallback_vision.id

    return selected


def _build_messages(payload: ChatRequest) -> list[dict]:
    messages: list[dict] = []
    has_images = len(payload.images) > 0

    for idx, item in enumerate(payload.messages):
        is_last_user = idx == len(payload.messages) - 1 and item.role == "user"
        if has_images and is_last_user:
            multimodal_parts = [{"type": "text", "text": item.content}]
            for image in payload.images:
                multimodal_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image,
                        },
                    }
                )
            messages.append({"role": item.role, "content": multimodal_parts})
        else:
            messages.append({"role": item.role, "content": item.content})
    return messages


async def stream_chat_completion(payload: ChatRequest) -> AsyncGenerator[str, None]:
    has_images = len(payload.images) > 0
    selected_model = resolve_model(payload.model, has_images=has_images)

    if not settings.model_api_key.strip():
        yield "未检测到 MODEL_API_KEY，请先在环境变量中配置后再试。"
        return

    endpoint = f"{settings.model_base_url.rstrip('/')}/chat/completions"
    body = {
        "model": selected_model,
        "stream": True,
        "messages": _build_messages(payload),
    }
    headers = {
        "Authorization": f"Bearer {settings.model_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", endpoint, headers=headers, json=body) as response:
                if response.status_code >= 400:
                    detail_raw = await response.aread()
                    detail = detail_raw.decode("utf-8", errors="ignore").strip()
                    yield f"模型调用失败（HTTP {response.status_code}）：{detail or '请检查模型配置。'}"
                    return
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    data = line.replace("data:", "", 1).strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        break

                    try:
                        payload_json = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = payload_json.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content
                    elif isinstance(content, list):
                        for segment in content:
                            text = segment.get("text") if isinstance(segment, dict) else None
                            if text:
                                yield text
    except Exception as exc:  # noqa: BLE001
        yield f"模型调用异常：{exc}"
