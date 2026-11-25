import { useEffect, useRef, useState } from "react";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const newSessionId = () => "s-" + Math.random().toString(36).slice(2, 10);

function errorText(status, body) {
  if (status === 503) return "All AI providers are unavailable right now. Try again in a moment.";
  if (status === 422) {
    const first = Array.isArray(body?.detail) ? body.detail[0] : null;
    const field = first?.loc?.[first.loc.length - 1];
    if (field === "message") return "Your message must be between 1 and 4000 characters.";
    return "The request was not valid. Check your message and try again.";
  }
  return typeof body?.detail === "string" ? body.detail : "Something went wrong. Try again.";
}

export default function App() {
  const [sessionId] = useState(newSessionId); // new session on every page load
  const [items, setItems] = useState([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulate, setSimulate] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, busy]);

  async function send() {
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setItems((x) => [...x, { kind: "user", text: message }]);
    try {
      const headers = { "Content-Type": "application/json" };
      if (simulate.trim()) headers["X-Simulate-Failure"] = simulate.trim();
      const body = { session_id: sessionId, message };
      if (systemPrompt.trim()) body.system_prompt = systemPrompt.trim();
      const res = await fetch(`${API}/chat`, { method: "POST", headers, body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw { status: res.status, data };
      setItems((x) => [...x, { kind: "assistant", text: data.reply, meta: data.metadata }]);
    } catch (e) {
      const text = e.status ? errorText(e.status, e.data) : "Cannot reach the server. Check your connection and try again.";
      setItems((x) => [...x, { kind: "error", text }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Chat</h1>
        <span className="sid">session {sessionId}</span>
      </header>

      <details className="settings">
        <summary>Session settings</summary>
        <label>
          System prompt
          <textarea data-testid="system-prompt-input" rows={2} value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)} placeholder="Default: helpful, concise assistant" />
        </label>
        <label>
          Simulate key failure (demo)
          <input value={simulate} onChange={(e) => setSimulate(e.target.value)} placeholder="key_1=429" />
        </label>
      </details>

      <main>
        {items.length === 0 && <p className="empty">Ask anything. Each reply shows where it came from and what it cost.</p>}
        {items.map((m, i) =>
          m.kind === "user" ? (
            <div key={i} className="msg user">{m.text}</div>
          ) : m.kind === "error" ? (
            <div key={i} className="msg error" role="alert">{m.text}</div>
          ) : (
            <div key={i} className="msg assistant" data-testid="assistant-message">
              <div className="text">{m.text}</div>
              <dl className="meta">
                <div><dt>Source</dt><dd data-testid="meta-source" className={m.meta.resolution_source}>{m.meta.resolution_source}</dd></div>
                <div><dt>Model</dt><dd data-testid="meta-model">{m.meta.model}</dd></div>
                <div><dt>Latency</dt><dd data-testid="meta-latency">{m.meta.latency_ms} ms</dd></div>
                <div><dt>Input tokens</dt><dd data-testid="meta-input-tokens">{m.meta.input_tokens}</dd></div>
                <div><dt>Output tokens</dt><dd data-testid="meta-output-tokens">{m.meta.output_tokens}</dd></div>
                <div><dt>Key</dt><dd>{m.meta.key_id ?? "none"}{m.meta.fallback_attempts > 0 ? ` (after ${m.meta.fallback_attempts} failed)` : ""}</dd></div>
              </dl>
            </div>
          )
        )}
        {busy && <div className="msg assistant pending">Thinkingâ€¦</div>}
        <div ref={endRef} />
      </main>

      <footer>
        <textarea data-testid="chat-input" rows={1} value={input} placeholder="Write a message"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <button data-testid="send-button" onClick={send} disabled={busy}>Send</button>
      </footer>
    </div>
  );
}
