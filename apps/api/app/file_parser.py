from pathlib import Path
from urllib.parse import urlparse
import requests
from fastapi import UploadFile
from langchain_community.document_loaders import BSHTMLLoader, PyPDFLoader, TextLoader, UnstructuredPowerPointLoader, WebBaseLoader
from langchain_community.document_loaders.word_document import Docx2txtLoader, UnstructuredWordDocumentLoader


TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log"}
HTML_SUFFIXES = {".html", ".htm"}
WORD_SUFFIXES = {".doc", ".docx"}
PPT_SUFFIXES = {".ppt", ".pptx"}
WEB_LINK_SUFFIXES = {".url", ".webloc", ".web"}


def _truncate(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}\n\n[...内容过长，已截断...]"


def _normalize_documents(documents: list, max_chars: int) -> str:
    chunks: list[str] = []
    for index, document in enumerate(documents):
        text = getattr(document, "page_content", "")
        text = "\n".join(line.rstrip() for line in str(text).splitlines() if line.strip())
        if not text:
            continue
        metadata = getattr(document, "metadata", {}) or {}
        page = metadata.get("page")
        source = metadata.get("source")
        label_parts: list[str] = []
        if page is not None:
            label_parts.append(f"page={page}")
        if source and index == 0:
            label_parts.append(f"source={Path(str(source)).name}")
        label = f"[{', '.join(label_parts)}]\n" if label_parts else ""
        chunks.append(f"{label}{text}")

    merged = "\n\n".join(chunks).strip()
    if not merged:
        return "文件解析完成，但未提取到可用文本内容。"
    return _truncate(merged, max_chars)


def _extract_url_from_text(raw_text: str) -> str:
    for line in raw_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.upper().startswith("URL="):
            candidate = candidate[4:].strip()
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return ""


async def _read_upload_text(file: UploadFile) -> str:
    content = await file.read()
    await file.seek(0)
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


async def save_upload_file(upload_dir: str, file: UploadFile) -> dict:
    base = Path(upload_dir)
    base.mkdir(parents=True, exist_ok=True)

    destination = base / file.filename
    content = await file.read()
    destination.write_bytes(content)
    await file.seek(0)

    return {
        "filename": file.filename,
        "size": len(content),
        "path": str(destination),
    }


async def parse_uploaded_file(upload_dir: str, file: UploadFile, max_chars: int, web_fetch_timeout_sec: int) -> dict:
    saved = await save_upload_file(upload_dir, file)
    path = Path(saved["path"])
    suffix = path.suffix.lower()
    kind = "text"

    try:
        if suffix in TEXT_SUFFIXES:
            loader = TextLoader(str(path), encoding="utf-8", autodetect_encoding=True)
            kind = "text"
        elif suffix == ".pdf":
            loader = PyPDFLoader(str(path))
            kind = "pdf"
        elif suffix == ".docx":
            loader = Docx2txtLoader(str(path))
            kind = "word"
        elif suffix == ".doc":
            loader = UnstructuredWordDocumentLoader(str(path))
            kind = "word"
        elif suffix in PPT_SUFFIXES:
            loader = UnstructuredPowerPointLoader(str(path))
            kind = "ppt"
        elif suffix in HTML_SUFFIXES:
            loader = BSHTMLLoader(str(path), open_encoding="utf-8")
            kind = "web"
        elif suffix in WEB_LINK_SUFFIXES:
            kind = "web"
            raw_text = await _read_upload_text(file)
            url = _extract_url_from_text(raw_text)
            if not url:
                raise ValueError("未找到可用的网页链接")
            # Disable inherited proxy settings to avoid local proxy side effects.
            session = requests.Session()
            session.trust_env = False
            loader = WebBaseLoader(
                web_paths=[url],
                requests_per_second=max(1, int(30 / max(web_fetch_timeout_sec, 1))),
                requests_kwargs={"timeout": web_fetch_timeout_sec, "verify": False},
                session=session,
            )
        else:
            raise ValueError("暂不支持该文件类型")

        documents = loader.load()
        content = _normalize_documents(documents, max_chars)
    except Exception as exc:  # noqa: BLE001
        return {
            "filename": saved["filename"],
            "size": saved["size"],
            "kind": kind,
            "content": f"文件解析失败：{exc}",
        }

    return {
        "filename": saved["filename"],
        "size": saved["size"],
        "kind": kind,
        "content": content,
    }
