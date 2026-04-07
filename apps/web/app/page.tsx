"use client";

import { FormEvent, MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type ModelInfo = {
  id: string;
  name: string;
  capabilities: string[];
  is_default?: boolean;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  images?: Array<{
    name: string;
    data_url: string;
  }>;
  documents?: Array<{
    name: string;
    content: string;
    kind: string;
  }>;
};

type ImageAttachment = {
  id: string;
  name: string;
  dataUrl: string;
};

type DocumentAttachment = {
  id: string;
  name: string;
  content: string;
  kind: string;
};

type SessionItem = {
  id: string;
  title: string;
  updated_at: string;
};

const API_BASE = "/backend";
const MAX_IMAGE_DIMENSION = 1440;
const IMAGE_REENCODE_THRESHOLD = 1.2 * 1024 * 1024;
const MAX_ATTACHMENTS = 6;
const MAX_DOCUMENT_ATTACHMENTS = 6;
const STREAM_TIMEOUT_MS = 120000;

const defaultModels: ModelInfo[] = [
  { id: "qwen3.5-plus", name: "Qwen3.5 Plus", capabilities: ["text", "vision"], is_default: true },
  { id: "qwen-plus-latest", name: "Qwen Plus Latest", capabilities: ["text"] },
  { id: "qwen-turbo-latest", name: "Qwen Turbo Latest", capabilities: ["text"] },
  { id: "qwen-vl-max-latest", name: "Qwen VL Max Latest", capabilities: ["text", "vision"] }
];

function renderMessageContent(message: ChatMessage) {
  if (message.role === "assistant") {
    return (
      <div className="markdown-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
    );
  }

  return <div className="plain-message">{message.content}</div>;
}

export default function Page() {
  const [models, setModels] = useState<ModelInfo[]>(defaultModels);
  const [model, setModel] = useState(defaultModels[0].id);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [attachments, setAttachments] = useState<ImageAttachment[]>([]);
  const [documentAttachments, setDocumentAttachments] = useState<DocumentAttachment[]>([]);
  const [modelHint, setModelHint] = useState("");
  const [menuSessionId, setMenuSessionId] = useState("");
  const [booting, setBooting] = useState(true);
  const initializedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const composerFormRef = useRef<HTMLFormElement | null>(null);

  const canSend = useMemo(
    () => (input.trim().length > 0 || attachments.length > 0 || documentAttachments.length > 0) && !loading,
    [input, loading, attachments.length, documentAttachments.length]
  );

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    (async () => {
      try {
        await loadModels();
        await loadSessions();
      } finally {
        setBooting(false);
      }
    })();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    function onWindowClick(event: globalThis.MouseEvent) {
      const target = event.target as HTMLElement | null;
      if (!target) return;
      if (target.closest(".session-actions")) return;
      setMenuSessionId("");
    }

    window.addEventListener("click", onWindowClick);
    return () => window.removeEventListener("click", onWindowClick);
  }, []);

  async function loadModels() {
    try {
      const res = await fetch(`${API_BASE}/api/models`);
      if (!res.ok) return;
      const data: ModelInfo[] = await res.json();
      if (data.length > 0) {
        setModels(data);
        const preferred = data.find((item) => item.is_default) ?? data[0];
        setModel(preferred.id);
      }
    } catch {
      // keep defaults on network failure
    }
  }

  async function loadSessions(preferredId?: string) {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      if (!res.ok) return;

      const data: SessionItem[] = await res.json();
      setSessions(data);

      const targetId = preferredId ?? activeSessionId;
      if (data.length === 0) {
        await createSession();
        return;
      }

      const selected = data.find((item) => item.id === targetId) ?? data[0];
      await openSession(selected.id);
    } catch {
      // keep current state on network failure
    }
  }

  async function createSession() {
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "新会话" })
    });

    if (!res.ok) {
      return "";
    }

    const session: SessionItem = await res.json();
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(session.id);
    setMessages([]);
    return session.id;
  }

  async function openSession(sessionId: string) {
    setActiveSessionId(sessionId);
    setMenuSessionId("");
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`);
      if (!res.ok) return;
      const sessionMessages: ChatMessage[] = await res.json();
      setMessages(sessionMessages);
    } catch {
      // keep old messages when loading fails
    }
  }

  function formatUpdatedAt(updatedAt: string) {
    const date = new Date(updatedAt);
    if (Number.isNaN(date.getTime())) return "刚刚";
    return date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  async function renameSession(session: SessionItem) {
    const title = window.prompt("请输入新的会话名称", session.title)?.trim();
    if (!title || title === session.title) {
      setMenuSessionId("");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/sessions/${session.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title })
      });
      if (!res.ok) return;
      await loadSessions(activeSessionId || session.id);
    } finally {
      setMenuSessionId("");
    }
  }

  async function deleteSession(session: SessionItem) {
    const confirmed = window.confirm(`确认删除会话「${session.title}」吗？`);
    if (!confirmed) {
      setMenuSessionId("");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/sessions/${session.id}`, { method: "DELETE" });
      if (!res.ok) return;

      const remains = sessions.filter((item) => item.id !== session.id);
      if (remains.length === 0) {
        await createSession();
        await loadSessions();
      } else {
        const fallback = session.id === activeSessionId ? remains[0].id : activeSessionId;
        await loadSessions(fallback);
      }
    } finally {
      setMenuSessionId("");
    }
  }

  function onSessionMenuToggle(event: MouseEvent<HTMLButtonElement>, sessionId: string) {
    event.stopPropagation();
    setMenuSessionId((current) => (current === sessionId ? "" : sessionId));
  }

  function getModelById(modelId: string) {
    return models.find((item) => item.id === modelId);
  }

  async function readFileAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("image read failed"));
      reader.readAsDataURL(file);
    });
  }

  async function loadImageElement(dataUrl: string): Promise<HTMLImageElement> {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("image decode failed"));
      image.src = dataUrl;
    });
  }

  async function fileToDataUrl(file: File): Promise<string> {
    const originalDataUrl = await readFileAsDataUrl(file);
    const shouldOptimize = file.size > IMAGE_REENCODE_THRESHOLD;

    try {
      const image = await loadImageElement(originalDataUrl);
      const longestSide = Math.max(image.naturalWidth, image.naturalHeight);
      const needsResize = longestSide > MAX_IMAGE_DIMENSION;

      if (!shouldOptimize && !needsResize) {
        return originalDataUrl;
      }

      const scale = Math.min(1, MAX_IMAGE_DIMENSION / longestSide);
      const width = Math.max(1, Math.round(image.naturalWidth * scale));
      const height = Math.max(1, Math.round(image.naturalHeight * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;

      const context = canvas.getContext("2d");
      if (!context) {
        return originalDataUrl;
      }

      context.drawImage(image, 0, 0, width, height);
      return canvas.toDataURL("image/jpeg", 0.86);
    } catch {
      return originalDataUrl;
    }
  }

  async function appendImages(files: FileList | File[]) {
    const incoming = Array.from(files).filter((file) => file.type.startsWith("image/"));
    if (incoming.length === 0) return;

    const converted = await Promise.all(
      incoming.map(async (file) => ({
        id: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
        name: file.name,
        dataUrl: await fileToDataUrl(file)
      }))
    );

    setAttachments((prev) => [...prev, ...converted].slice(0, MAX_ATTACHMENTS));
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => prev.filter((item) => item.id !== id));
  }

  function removeDocumentAttachment(id: string) {
    setDocumentAttachments((prev) => prev.filter((item) => item.id !== id));
  }

  function buildMessageImages(items: ImageAttachment[]) {
    return items.map((item) => ({
      name: item.name,
      data_url: item.dataUrl
    }));
  }

  function buildMessageDocuments(items: DocumentAttachment[]) {
    return items.map((item) => ({
      name: item.name,
      content: item.content,
      kind: item.kind
    }));
  }

  async function appendDocuments(files: FileList | File[]) {
    const incoming = Array.from(files);
    if (incoming.length === 0) return;

    const formData = new FormData();
    incoming.forEach((file) => formData.append("files", file));

    const res = await fetch(`${API_BASE}/api/files/parse`, {
      method: "POST",
      body: formData
    });
    if (!res.ok) {
      throw new Error("document parse failed");
    }

    const data = await res.json();
    const parsed: DocumentAttachment[] = (data.files || []).map((item: { filename: string; content: string; kind?: string }) => ({
      id: `${item.filename}-${Math.random().toString(36).slice(2, 8)}`,
      name: item.filename,
      content: item.content,
      kind: item.kind || "text"
    }));

    setDocumentAttachments((prev) => [...prev, ...parsed].slice(0, MAX_DOCUMENT_ATTACHMENTS));
  }

  function resolveModelForRequest() {
    if (attachments.length === 0) {
      setModelHint("");
      return model;
    }

    const current = getModelById(model);
    if (current?.capabilities.includes("vision")) {
      setModelHint("");
      return model;
    }

    const visionModel = models.find((item) => item.capabilities.includes("vision"));
    if (visionModel) {
      setModel(visionModel.id);
      setModelHint(`检测到图片，已自动切换到视觉模型：${visionModel.name}`);
      return visionModel.id;
    }

    setModelHint("检测到图片，但当前没有可用视觉模型，已使用当前模型继续。\n你可以在模型列表中配置视觉模型。\n");
    return model;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSend) return;

    let sessionId = activeSessionId;
    if (!sessionId) {
      sessionId = await createSession();
    }
    if (!sessionId) {
      return;
    }

    const hasImages = attachments.length > 0;
    const hasDocuments = documentAttachments.length > 0;
    const userText = input.trim() || (hasImages ? "请分析我上传的图片。" : hasDocuments ? "请结合我上传的文档回答问题。" : "");
    const requestModel = resolveModelForRequest();
    const messageImages = buildMessageImages(attachments);
    const messageDocuments = buildMessageDocuments(documentAttachments);

    setInput("");
    setLoading(true);
    setAttachments([]);
    setDocumentAttachments([]);

    const next = [...messages, { role: "user", content: userText, images: messageImages, documents: messageDocuments } as ChatMessage];
    setMessages([...next, { role: "assistant", content: "" }]);

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);

    try {

      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          model: requestModel,
          session_id: sessionId,
          messages: [{ role: "user", content: userText, images: messageImages, documents: messageDocuments }],
          images: []
        })
      });

      if (!res.ok || !res.body) {
        window.clearTimeout(timeoutId);
        throw new Error("stream unavailable");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop() ?? "";

        for (const eventChunk of events) {
          const lines = eventChunk.split(/\r?\n/);
          const payloadLines: string[] = [];

          for (const rawLine of lines) {
            const line = rawLine.trimEnd();
            if (!line.startsWith("data:")) continue;
            payloadLines.push(line.slice(5).trimStart());
          }

          if (payloadLines.length === 0) continue;

          const payloadText = payloadLines.join("\n");
          if (!payloadText || payloadText === "[DONE]") continue;

          let piece = payloadText;
          try {
            const parsed = JSON.parse(payloadText) as { token?: string };
            if (typeof parsed.token === "string") {
              piece = parsed.token;
            }
          } catch {
            // Backward-compatible fallback for plain `data: token` payloads.
          }

          if (!piece) continue;

          setMessages((current) => {
            const updated = [...current];
            const last = updated.at(-1);
            if (!last || last.role !== "assistant") {
              updated.push({ role: "assistant", content: piece });
              return updated;
            }
            updated[updated.length - 1] = { ...last, content: `${last.content}${piece}` };
            return updated;
          });
        }

        if (done) break;
      }

    } catch (error) {
      const timeoutMessage = error instanceof DOMException && error.name === "AbortError"
        ? "请求超时，已自动停止。请重试，或减少上下文/图片数量后再发送。"
        : "请求失败，请稍后重试。";
      setMessages([...next, { role: "assistant", content: timeoutMessage }]);
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
      await loadSessions(sessionId);
    }
  }

  return (
    <main className="app-shell">
      <div className="workspace-grid">
        <aside className="history-panel">
          <header className="history-header">
            <div className="history-avatar-wrap" aria-label="Ciallo 形象位">
              <img
                src="/ciallo.png"
                alt="Ciallo 卡通形象"
                className="history-avatar"
              />
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={async () => {
                const id = await createSession();
                if (id) {
                  await loadSessions(id);
                }
              }}
            >
              新建
            </button>
          </header>

          <section className="session-list">
            {sessions.length === 0 ? (
              <div className="session-empty">暂无历史会话</div>
            ) : (
              sessions.map((item) => (
                <article key={item.id} className={item.id === activeSessionId ? "session-item session-item-active" : "session-item"}>
                  <button
                    type="button"
                    className="session-main"
                    onClick={() => openSession(item.id)}
                  >
                    <div className="session-item-title">{item.title}</div>
                    <div className="session-item-time">{formatUpdatedAt(item.updated_at)}</div>
                  </button>

                  <div className="session-actions">
                    <button
                      type="button"
                      className="session-menu-button"
                      onClick={(event) => onSessionMenuToggle(event, item.id)}
                    >
                      ...
                    </button>
                    {menuSessionId === item.id ? (
                      <div className="session-actions-menu">
                        <button type="button" className="session-action-item" onClick={() => renameSession(item)}>
                          重命名
                        </button>
                        <button type="button" className="session-action-item session-action-danger" onClick={() => deleteSession(item)}>
                          删除
                        </button>
                      </div>
                    ) : null}
                  </div>
                </article>
              ))
            )}
          </section>
        </aside>

        <div className="chat-card">
          <header className="chat-header">
            <div>
              <div className="brand-title">Ciallo～(∠・ω&lt; )⌒☆</div>
            </div>
          </header>

          <section className="toolbar">
            <label htmlFor="model" className="toolbar-label">
              当前模型
            </label>
            <select
              id="model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="model-select"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.capabilities.join("+")})
                </option>
              ))}
            </select>
          </section>

          {modelHint ? <section className="hint-banner">{modelHint}</section> : null}

          <section className="messages-panel">
            {booting ? (
              <div className="empty-state">正在加载会话...</div>
            ) : messages.length === 0 ? (
              <div className="empty-state">
                Ciallo～(∠・ω&lt; )⌒☆
                <br />
                欢迎回来，今天想聊点什么？
              </div>
            ) : (
              messages.map((msg, idx) => (
                <article
                  key={`${msg.role}-${idx}`}
                  className={msg.role === "user" ? "message-bubble message-user" : "message-bubble message-assistant"}
                >
                  {msg.images?.length ? (
                    <div className="message-image-grid">
                      {msg.images.map((image, imageIdx) => (
                        <div key={`${image.name}-${imageIdx}`} className="message-image-card">
                          <img src={image.data_url} alt={image.name} className="message-image-preview" />
                          <div className="message-image-name" title={image.name}>{image.name}</div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {msg.documents?.length ? (
                    <div className="message-doc-grid">
                      {msg.documents.map((doc, docIdx) => (
                        <div key={`${doc.name}-${docIdx}`} className="message-doc-card">
                          <div className="message-doc-title">{doc.name}</div>
                          <div className="message-doc-kind">{doc.kind}</div>
                          <div className="message-doc-preview">{doc.content}</div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {renderMessageContent(msg)}
                </article>
              ))
            )}
            <div ref={messagesEndRef} />
          </section>

          <form ref={composerFormRef} onSubmit={onSubmit} className="composer">
            <div className="composer-stack">
              <div className="composer-tools">
                <input
                  ref={uploadInputRef}
                  type="file"
                  multiple
                  accept="image/*,.txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.html,.htm,.url,.webloc,.web"
                  hidden
                  onChange={async (e) => {
                    const input = e.currentTarget;
                    const files = Array.from(input.files ?? []);
                    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
                    const docFiles = files.filter((file) => !file.type.startsWith("image/"));

                    try {
                      if (imageFiles.length > 0) {
                        await appendImages(imageFiles);
                      }
                      if (docFiles.length > 0) {
                        await appendDocuments(docFiles);
                      }
                      if (files.length > 0) {
                        setModelHint("");
                      }
                    } catch {
                      setModelHint("文件解析失败，请检查格式后重试。");
                    } finally {
                      input.value = "";
                    }
                  }}
                />
                <button
                  type="button"
                  className="add-button"
                  onClick={() => uploadInputRef.current?.click()}
                  aria-label="添加图片或文档"
                  title="添加图片或文档"
                >
                  +
                </button>
                <span className="composer-tools-hint">添加图片或文件</span>
              </div>

              {attachments.length > 0 ? (
                <section className="composer-attachment-strip">
                  {attachments.map((item) => (
                    <article key={item.id} className="composer-attachment-item">
                      <img src={item.dataUrl} alt={item.name} className="composer-attachment-preview" />
                      <div className="attachment-name" title={item.name}>{item.name}</div>
                      <button type="button" className="attachment-remove" onClick={() => removeAttachment(item.id)}>
                        移除
                      </button>
                    </article>
                  ))}
                </section>
              ) : null}

              {documentAttachments.length > 0 ? (
                <section className="composer-doc-strip">
                  {documentAttachments.map((item) => (
                    <article key={item.id} className="composer-doc-item">
                      <div className="composer-doc-name" title={item.name}>{item.name}</div>
                      <div className="composer-doc-kind">{item.kind}</div>
                      <div className="composer-doc-preview">{item.content}</div>
                      <button type="button" className="attachment-remove" onClick={() => removeDocumentAttachment(item.id)}>
                        移除
                      </button>
                    </article>
                  ))}
                </section>
              ) : null}

              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (canSend && !loading) {
                      composerFormRef.current?.requestSubmit();
                    }
                  }
                }}
                onPaste={async (e) => {
                  const items = Array.from(e.clipboardData.items || []);
                  const imageFiles = items
                    .filter((item) => item.type.startsWith("image/"))
                    .map((item) => item.getAsFile())
                    .filter((file): file is File => Boolean(file));

                  if (imageFiles.length > 0) {
                    e.preventDefault();
                    await appendImages(imageFiles);
                  }
                }}
                placeholder="输入你的问题..."
                className="composer-input"
                rows={3}
              />
            </div>
            <button
              disabled={!canSend}
              className="send-button"
            >
              {loading ? "生成中" : "发送"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
