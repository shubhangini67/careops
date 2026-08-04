"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useChatSession } from "@/context/ChatSessionContext";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import VoiceRecordButton from "@/components/planning/VoiceRecordButton";

// Hues reused directly from Sidebar.tsx's NAV_LINKS (Analytics/Action
// Center/Market/AI Assistant/Planning), not invented for this page -- ties
// the chat page into the same category-color language the rest of the app
// already establishes, instead of introducing a new palette.
const SUGGESTIONS = [
  { category: "Quality",    hue: "#38bdf8", icon: "◆", q: "Which run had the lowest safety score and why?" },
  { category: "Safety",     hue: "#fb7185", icon: "◈", q: "What are the most common safety incidents recently?" },
  { category: "Supplies",   hue: "#a855f7", icon: "◉", q: "Which supply items are flagged as low stock most often?" },
  { category: "Capacity",   hue: "#34d399", icon: "◇", q: "Which departments show up most in recent plans?" },
  { category: "Forecast",   hue: "#818cf8", icon: "◎", q: "Which scenario had the highest predicted admissions?" },
  { category: "Strategy",   hue: "#B0621A", icon: "◐", q: "If I had to focus on one thing to improve our safety score, what would it be?" },
];

export default function ChatPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const {
    messages, busy, sessionId, sessionList, sessionListLoading,
    send, startNewSession, loadSession, deleteSession, refreshSessionList,
  } = useChatSession();
  const [input, setInput]       = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const bottomRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [user, authLoading, router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    refreshSessionList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Lets the /planning results page's "Ask the AI" box hand off a typed
  // question via ?q= instead of building a second inline chat interface
  // there -- reads window.location directly (not useSearchParams) so this
  // page doesn't need a Suspense-boundary restructure for one query param.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      send_(q);
      window.history.replaceState({}, "", "/chat");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function send_(question: string) {
    if (!question.trim() || busy) return;
    setInput("");
    send(question);
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send_(input); }
  }

  async function handleDelete(id: number) {
    setConfirmDeleteId(null);
    try { await deleteSession(id); } catch { /* list just keeps the stale row on failure */ }
  }

  if (authLoading || !user) return null;

  const empty   = messages.length === 0;
  const initials = (user.full_name ?? user.email).slice(0, 2).toUpperCase();

  return (
    <main className="flex h-[calc(100vh-56px)] page-canvas relative overflow-hidden">

      {/* ── History sidebar ─────────────────────────────────────── */}
      <div className={`${historyOpen ? "w-64" : "w-0"} shrink-0 overflow-hidden border-r border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] transition-all duration-200`}>
        <div className="flex h-full w-64 flex-col">
          <div className="flex items-center justify-between px-4 py-3.5 border-b border-[var(--color-border-default)]">
            <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-text-faint)]">Conversations</span>
            <button
              onClick={() => { startNewSession(); setInput(""); }}
              className="rounded-full bg-[var(--color-accent-soft)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-white"
            >
              + New
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-2.5 py-3 space-y-1.5">
            {sessionListLoading && sessionList.length === 0 && (
              <p className="px-2 py-2 text-[11px] text-[var(--color-text-faint)]">Loading…</p>
            )}
            {!sessionListLoading && sessionList.length === 0 && (
              <p className="px-2 py-2 text-[11px] text-[var(--color-text-faint)]">No past conversations yet.</p>
            )}
            {sessionList.map((s) => {
              const active = s.id === sessionId;
              return (
              <div
                key={s.id}
                className={`group relative flex items-center gap-1 rounded-xl border transition-all ${
                  active
                    ? "border-[var(--color-accent)]/40 bg-[var(--color-accent-soft)] shadow-[0_2px_6px_rgba(255,82,0,0.10)]"
                    : "border-[var(--color-border-default)] bg-[var(--color-surface-raised)] shadow-[0_1px_2px_rgba(20,15,5,0.04)] hover:border-[var(--color-accent)]/30 hover:shadow-[0_4px_12px_rgba(20,15,5,0.08)]"
                }`}
              >
                {active && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--color-accent)]" />}
                <button
                  onClick={() => loadSession(s.id)}
                  className={`flex flex-1 min-w-0 items-center gap-2.5 rounded-xl px-3 py-2.5 text-left transition-colors ${active ? "pl-4" : ""}`}
                >
                  <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
                    active ? "bg-[var(--color-accent)] text-white" : "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  }`}>
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
                  </span>
                  <span className={`min-w-0 truncate text-[12.5px] ${
                    active ? "font-bold text-[var(--color-accent)]" : "font-medium text-[var(--color-text-primary)]"
                  }`}>
                    {s.title || "Untitled conversation"}
                  </span>
                </button>

                {confirmDeleteId === s.id ? (
                  <div className="flex shrink-0 items-center gap-1 pr-1.5">
                    <button
                      onClick={() => handleDelete(s.id)}
                      title="Confirm delete"
                      className="rounded-md p-1 text-[var(--color-critical)] hover:bg-[var(--color-critical-soft)]"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                    </button>
                    <button
                      onClick={() => setConfirmDeleteId(null)}
                      title="Cancel"
                      className="rounded-md p-1 text-[var(--color-text-faint)] hover:bg-[var(--color-surface-sunken)]"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDeleteId(s.id)}
                    title="Delete conversation"
                    className="shrink-0 rounded-md p-1.5 text-[var(--color-text-ghost)] opacity-0 transition-opacity hover:bg-[var(--color-critical-soft)] hover:text-[var(--color-critical)] group-hover:opacity-100"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                )}
              </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col relative">
        {/* Ambient glow */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="h-[500px] w-[700px] rounded-full opacity-[0.06]"
            style={{ background: "radial-gradient(closest-side, #e6892a, transparent)" }} />
        </div>

        {/* History toggle */}
        <button
          onClick={() => setHistoryOpen(o => !o)}
          className="absolute left-3 top-3 z-10 rounded-lg p-1.5 text-[var(--color-text-faint)] hover:bg-[var(--color-surface-raised)] hover:text-[var(--color-text-primary)]"
          title={historyOpen ? "Hide history" : "Show history"}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h7" />
          </svg>
        </button>

        {/* ── Message area ─────────────────────────────────────────── */}
        <div className="relative flex-1 overflow-y-auto">
          <div className="mx-auto max-w-2xl px-4 py-8">

            {/* ── Empty state ─────────────────────────── */}
            {empty && (
              <div className="pt-6 pb-4">
                {/* Header */}
                <div className="text-center mb-10">
                  <div className="inline-flex items-center gap-2 rounded-full border border-ember-500/20 bg-ember-500/[0.07] px-4 py-1.5 mb-5">
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="absolute inset-0 animate-ping rounded-full bg-ember-400 opacity-60" />
                      <span className="relative rounded-full bg-ember-400" />
                    </span>
                    <span className="text-[10px] uppercase tracking-[0.26em] text-[var(--color-accent)]">
                      Your policy assistant
                    </span>
                  </div>

                  <h1 className="text-[34px] font-semibold tracking-[-0.02em] text-[var(--color-text-primary)] leading-[1.05]">
                    Ask about{" "}
                    <span className="display-it text-[var(--color-accent)]">{user.org_name}</span>
                  </h1>
                  <p className="mt-3 text-[13px] leading-[1.7] text-[var(--color-text-faint)] max-w-xs mx-auto">
                    Answers come from your run history, capacity data, supply levels, and hospital policies. Not generic AI.
                  </p>
                </div>

                {/* Suggestion grid */}
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {SUGGESTIONS.map(({ category, hue, icon, q }) => (
                    <button
                      key={q}
                      onClick={() => send_(q)}
                      className="card group relative flex items-start gap-3 px-4 py-3.5 text-left"
                    >
                      <span
                        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[13px] font-semibold"
                        style={{ background: `${hue}1f`, color: hue }}
                      >
                        {icon}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[9px] uppercase tracking-[0.2em] mb-1 transition-colors" style={{ color: `${hue}b0` }}>{category}</p>
                        <p className="text-[13px] text-[var(--color-text-soft)] leading-snug group-hover:text-[var(--color-text-primary)] transition-colors">{q}</p>
                      </div>
                      <svg className="mt-1 h-3.5 w-3.5 shrink-0 text-[var(--color-text-ghost)] group-hover:text-[var(--color-accent)]/50 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                      </svg>
                    </button>
                  ))}
                </div>

                {/* Model badge */}
                <p className="mt-6 text-center text-[9px] uppercase tracking-[0.22em] text-[var(--color-text-ghost)]">
                  llama-3.3-70b · RAG over your runs & feedback
                </p>
              </div>
            )}

            {/* ── Messages ────────────────────────────── */}
            <div className="space-y-5">
              {messages.map((msg, i) => (
                <div key={i} className={`flex items-start gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>

                  {/* Avatar */}
                  {msg.role === "assistant" ? (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-b from-ember-500/30 to-ember-600/20 ring-1 ring-ember-400/25 mt-0.5">
                      <span className="text-[9px] font-bold text-[var(--color-accent)]">CO</span>
                    </div>
                  ) : (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[var(--color-accent-soft)] ring-1 ring-[var(--color-accent)]/30 mt-0.5">
                      <span className="text-[9px] font-bold text-[var(--color-accent)]">{initials}</span>
                    </div>
                  )}

                  {/* Bubble */}
                  <div className={`max-w-[82%] rounded-2xl px-4 py-3 text-[13.5px] leading-relaxed shadow-[0_1px_2px_rgba(20,15,5,0.05),0_10px_28px_-14px_rgba(20,15,5,0.22)] ${
                    msg.role === "user"
                      ? "rounded-tr-sm bg-[var(--color-accent-soft)] ring-1 ring-[var(--color-accent)]/25 text-[var(--color-text-primary)]"
                      : "rounded-tl-sm bg-[var(--color-surface-raised)] ring-1 ring-[var(--color-border-default)] text-[var(--color-text-primary)]"
                  }`}>
                    {/* Thinking dots */}
                    {!msg.content && msg.streaming && (
                      <span className="inline-flex gap-1.5 items-center py-0.5">
                        {[0, 150, 300].map(d => (
                          <span key={d} className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)] animate-bounce"
                            style={{ animationDelay: `${d}ms` }} />
                        ))}
                      </span>
                    )}

                    {/* User message */}
                    {msg.content && msg.role === "user" && (
                      <span>{msg.content}</span>
                    )}

                    {/* Assistant message with markdown */}
                    {msg.content && msg.role === "assistant" && (
                      <div className="prose-chat">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                        {msg.streaming && (
                          <span className="inline-block h-[14px] w-[2px] rounded-full bg-ember-400 animate-pulse ml-0.5 translate-y-[2px]" />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div ref={bottomRef} className="h-4" />
          </div>
        </div>

        {/* ── Input bar ───────────────────────────────────────────── */}
        <div className="relative border-t border-[var(--color-border-default)] bg-white/95 px-4 pb-5 pt-4 backdrop-blur-md dark:bg-[var(--color-surface-page)]/95">
          <div className="mx-auto max-w-2xl">

            {/* Input card */}
            <div className="relative rounded-2xl border-2 border-[var(--color-border-default)] bg-[var(--color-surface-raised)] shadow-[0_2px_4px_rgba(20,15,5,0.06),0_16px_36px_-16px_rgba(20,15,5,0.28)] transition-all duration-200 focus-within:border-[var(--color-accent)] focus-within:shadow-[0_0_0_4px_rgba(255,82,0,0.10),0_16px_36px_-16px_rgba(20,15,5,0.28)]">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
                }}
                onKeyDown={handleKey}
                placeholder="Ask anything about hospital operations, policies, or past runs…"
                disabled={busy}
                className="w-full resize-none bg-transparent px-5 pt-4 pb-12 text-[14.5px] font-medium text-[var(--color-text-primary)] placeholder:font-normal placeholder:text-[var(--color-text-faint)] focus:outline-none disabled:opacity-40"
                style={{ maxHeight: "120px" }}
              />

              {/* Footer row inside card */}
              <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between border-t border-[var(--color-border-soft)] px-4 py-2.5">
                <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--color-accent)]">
                  {busy ? (
                    <>
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent)]" />
                      Thinking…
                    </>
                  ) : (
                    "Enter ↵ to send"
                  )}
                </span>
                <div className="flex items-center gap-2">
                  <VoiceRecordButton onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))} disabled={busy} />
                  <button
                    onClick={() => send_(input)}
                    disabled={busy || !input.trim()}
                    className="flex items-center gap-1.5 rounded-xl bg-[var(--color-accent)] px-4 py-2 text-[12px] font-bold text-white shadow-[0_2px_8px_rgba(255,82,0,0.28)] transition-all hover:bg-[var(--color-hero-bg)] hover:shadow-[0_4px_14px_rgba(255,82,0,0.38)] disabled:bg-[var(--color-surface-sunken)] disabled:text-[var(--color-text-ghost)] disabled:shadow-none disabled:cursor-not-allowed"
                  >
                    {busy ? (
                      <span className="flex gap-1">
                        {[0,100,200].map(d => (
                          <span key={d} className="h-1 w-1 rounded-full bg-white animate-bounce"
                            style={{ animationDelay: `${d}ms` }} />
                        ))}
                      </span>
                    ) : (
                      <>
                        Send
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* New conversation */}
            {messages.length > 0 && (
              <div className="mt-2.5 flex justify-center">
                <button
                  onClick={startNewSession}
                  className="text-[9px] uppercase tracking-[0.2em] text-[var(--color-text-ghost)] transition-colors hover:text-[var(--color-text-faint)]"
                >
                  Start new conversation
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
