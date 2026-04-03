"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

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
};

type ImageAttachment = {
  id: string;
  name: string;
  dataUrl: string;
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
const STREAM_TIMEOUT_MS = 120000;

const defaultModels: ModelInfo[] = [
  { id: "qwen3.5-plus", name: "Qwen3.5 Plus", capabilities: ["text", "vision"], is_default: true },
  { id: "qwen-plus-latest", name: "Qwen Plus Latest", capabilities: ["text"] },
  { id: "qwen-turbo-latest", name: "Qwen Turbo Latest", capabilities: ["text"] },
  { id: "qwen-vl-max-latest", name: "Qwen VL Max Latest", capabilities: ["text", "vision"] }
];

export default function Page() {
  const [models, setModels] = useState<ModelInfo[]>(defaultModels);
  const [model, setModel] = useState(defaultModels[0].id);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [attachments, setAttachments] = useState<ImageAttachment[]>([]);
  const [modelHint, setModelHint] = useState("");
  const [booting, setBooting] = useState(true);
  const initializedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const composerFormRef = useRef<HTMLFormElement | null>(null);

  const canSend = useMemo(() => (input.trim().length > 0 || attachments.length > 0) && !loading, [input, loading, attachments.length]);

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

  function buildMessageImages(items: ImageAttachment[]) {
    return items.map((item) => ({
      name: item.name,
      data_url: item.dataUrl
    }));
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
    const userText = input.trim() || (hasImages ? "请分析我上传的图片。" : "");
    const requestModel = resolveModelForRequest();
    const messageImages = buildMessageImages(attachments);

    setInput("");
    setLoading(true);
    setAttachments([]);

    const next = [...messages, { role: "user", content: userText, images: messageImages } as ChatMessage];
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
          messages: [{ role: "user", content: userText, images: messageImages }],
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

        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";

        for (const rawLine of lines) {
          const line = rawLine.trimEnd();
          if (!line.startsWith("data:")) continue;
          const piece = line.slice(5).trimStart();
          if (!piece || piece === "[DONE]") continue;
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
            <div>
              <div className="history-title">会话历史</div>
              <div className="history-subtitle">可持续上下文对话</div>
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
                <button
                  key={item.id}
                  type="button"
                  className={item.id === activeSessionId ? "session-item session-item-active" : "session-item"}
                  onClick={() => openSession(item.id)}
                >
                  <div className="session-item-title">{item.title}</div>
                  <div className="session-item-time">{formatUpdatedAt(item.updated_at)}</div>
                </button>
              ))
            )}
          </section>
        </aside>

        <div className="chat-card">
          <header className="chat-header">
            <div>
              <div className="brand-title">Ciallo～(∠・ω&lt; )⌒☆</div>
              <div className="brand-subtitle">Galgame 风格智能体</div>
            </div>
            <button
              onClick={loadModels}
              className="ghost-button"
            >
              刷新模型
            </button>
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
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*"
              hidden
              onChange={async (e) => {
                const input = e.currentTarget;
                const files = input.files;
                if (files) {
                  await appendImages(files);
                }
                input.value = "";
              }}
            />
            <button
              type="button"
              className="ghost-button"
              onClick={() => fileInputRef.current?.click()}
            >
              上传图片
            </button>
          </section>

          {modelHint ? <section className="hint-banner">{modelHint}</section> : null}

          <section className="messages-panel">
            {booting ? (
              <div className="empty-state">正在加载会话...</div>
            ) : messages.length === 0 ? (
              <div className="empty-state">
                试试这些问题：
                <br />
                1. 帮我制定一份 7 天学习计划。
                <br />
                2. 根据这段文字做摘要并给出行动建议。
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
                  {msg.content}
                </article>
              ))
            )}
            <div ref={messagesEndRef} />
          </section>

          <form ref={composerFormRef} onSubmit={onSubmit} className="composer">
            <div className="composer-stack">
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
