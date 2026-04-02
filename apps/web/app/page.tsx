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
};

type ImageAttachment = {
  id: string;
  name: string;
  dataUrl: string;
};

const API_BASE = "/backend";

const defaultModels: ModelInfo[] = [
  { id: "qwen3.5-plus", name: "Qwen3.5 Plus", capabilities: ["text", "vision"], is_default: true },
  { id: "qwen-plus-latest", name: "Qwen Plus Latest", capabilities: ["text"] },
  { id: "qwen-turbo-latest", name: "Qwen Turbo Latest", capabilities: ["text"] },
  { id: "qwen-vl-max-latest", name: "Qwen VL Max Latest", capabilities: ["text", "vision"] }
];

export default function Page() {
  const [models, setModels] = useState<ModelInfo[]>(defaultModels);
  const [model, setModel] = useState(defaultModels[0].id);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [attachments, setAttachments] = useState<ImageAttachment[]>([]);
  const [modelHint, setModelHint] = useState("");
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const canSend = useMemo(() => (input.trim().length > 0 || attachments.length > 0) && !loading, [input, loading, attachments.length]);

  useEffect(() => {
    loadModels();
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

  function getModelById(modelId: string) {
    return models.find((item) => item.id === modelId);
  }

  async function fileToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("image read failed"));
      reader.readAsDataURL(file);
    });
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

    setAttachments((prev) => [...prev, ...converted].slice(0, 6));
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => prev.filter((item) => item.id !== id));
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

    const hasImages = attachments.length > 0;
    const userText = input.trim() || (hasImages ? "请分析我上传的图片。" : "");
    const requestModel = resolveModelForRequest();
    const imageTag = hasImages ? `\n[已附加 ${attachments.length} 张图片]` : "";
    const displayText = `${userText}${imageTag}`;

    setInput("");
    setLoading(true);

    const next = [...messages, { role: "user", content: displayText } as ChatMessage];
    setMessages([...next, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: requestModel,
          messages: [...messages, { role: "user", content: userText }],
          images: attachments.map((item) => item.dataUrl)
        })
      });

      if (!res.ok || !res.body) {
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
    } catch {
      setMessages([...next, { role: "assistant", content: "请求失败，请稍后重试。" }]);
    } finally {
      setLoading(false);
      setAttachments([]);
    }
  }

  return (
    <main className="app-shell">
      <div
        className="chat-card"
      >
        <header className="chat-header">
          <div>
            <div className="brand-title">Ciallo Agent</div>
            <div className="brand-subtitle">个人智能聊天助手</div>
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

        {attachments.length > 0 ? (
          <section className="attachment-strip">
            {attachments.map((item) => (
              <article key={item.id} className="attachment-item">
                <img src={item.dataUrl} alt={item.name} className="attachment-preview" />
                <div className="attachment-name" title={item.name}>{item.name}</div>
                <button type="button" className="attachment-remove" onClick={() => removeAttachment(item.id)}>
                  移除
                </button>
              </article>
            ))}
          </section>
        ) : null}

        <section className="messages-panel">
          {messages.length === 0 ? (
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
                {msg.content}
              </article>
            ))
          )}
          <div ref={messagesEndRef} />
        </section>

        <form onSubmit={onSubmit} className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
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
          <button
            disabled={!canSend}
            className="send-button"
          >
            {loading ? "生成中" : "发送"}
          </button>
        </form>
      </div>
    </main>
  );
}
