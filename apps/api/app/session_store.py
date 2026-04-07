import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .schemas import ChatDocument, ChatImage, ChatMessage, SessionItem


class SessionStore:
    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._lock = Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write_data({"sessions": []})

    def _read_data(self) -> dict:
        if not self._path.exists():
            return {"sessions": []}
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {"sessions": []}
            sessions = data.get("sessions")
            if isinstance(sessions, list):
                return {"sessions": sessions}
        except Exception:  # noqa: BLE001
            pass
        return {"sessions": []}

    def _write_data(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _find_session(self, sessions: list[dict], session_id: str) -> dict | None:
        for item in sessions:
            if item.get("id") == session_id:
                return item
        return None

    def list_sessions(self) -> list[SessionItem]:
        with self._lock:
            data = self._read_data()
            items: list[SessionItem] = []
            for item in data["sessions"]:
                items.append(
                    SessionItem(
                        id=item.get("id", ""),
                        title=item.get("title", "新会话"),
                        updated_at=item.get("updated_at", self._now()),
                    )
                )
            return sorted(items, key=lambda i: i.updated_at, reverse=True)

    def create_session(self, title: str | None = None) -> SessionItem:
        with self._lock:
            data = self._read_data()
            now = self._now()
            item = {
                "id": str(uuid4()),
                "title": (title or "新会话").strip() or "新会话",
                "updated_at": now,
                "messages": [],
            }
            data["sessions"].append(item)
            self._write_data(data)
            return SessionItem(id=item["id"], title=item["title"], updated_at=item["updated_at"])

    def rename_session(self, session_id: str, title: str) -> SessionItem | None:
        cleaned = title.strip() or "新会话"
        with self._lock:
            data = self._read_data()
            item = self._find_session(data["sessions"], session_id)
            if not item:
                return None

            item["title"] = cleaned
            item["updated_at"] = self._now()
            self._write_data(data)
            return SessionItem(id=item["id"], title=item["title"], updated_at=item["updated_at"])

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            data = self._read_data()
            original_len = len(data["sessions"])
            data["sessions"] = [item for item in data["sessions"] if item.get("id") != session_id]
            if len(data["sessions"]) == original_len:
                return False
            self._write_data(data)
            return True

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        with self._lock:
            data = self._read_data()
            item = self._find_session(data["sessions"], session_id)
            if not item:
                return []

            messages: list[ChatMessage] = []
            for message in item.get("messages", []):
                role = message.get("role")
                content = message.get("content")
                if isinstance(role, str) and isinstance(content, str):
                    images: list[ChatImage] = []
                    for image in message.get("images", []):
                        name = image.get("name") if isinstance(image, dict) else None
                        data_url = image.get("data_url") if isinstance(image, dict) else None
                        if isinstance(name, str) and isinstance(data_url, str):
                            images.append(ChatImage(name=name, data_url=data_url))

                    documents: list[ChatDocument] = []
                    for document in message.get("documents", []):
                        name = document.get("name") if isinstance(document, dict) else None
                        doc_content = document.get("content") if isinstance(document, dict) else None
                        kind = document.get("kind") if isinstance(document, dict) else "text"
                        if isinstance(name, str) and isinstance(doc_content, str):
                            documents.append(ChatDocument(name=name, content=doc_content, kind=str(kind or "text")))

                    messages.append(ChatMessage(role=role, content=content, images=images, documents=documents))
            return messages

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        images: list[ChatImage] | None = None,
        documents: list[ChatDocument] | None = None,
    ) -> bool:
        text = content.strip()
        serialized_images = [{"name": image.name, "data_url": image.data_url} for image in images or []]
        serialized_documents = [
            {"name": document.name, "content": document.content, "kind": document.kind}
            for document in documents or []
        ]
        if not text and not serialized_images and not serialized_documents:
            return False

        with self._lock:
            data = self._read_data()
            item = self._find_session(data["sessions"], session_id)
            if not item:
                return False

            item.setdefault("messages", []).append(
                {
                    "role": role,
                    "content": text,
                    "images": serialized_images,
                    "documents": serialized_documents,
                    "created_at": self._now(),
                }
            )
            if role == "user" and (item.get("title") in (None, "", "新会话")):
                item["title"] = text[:24] or "新会话"
            item["updated_at"] = self._now()
            self._write_data(data)
            return True
