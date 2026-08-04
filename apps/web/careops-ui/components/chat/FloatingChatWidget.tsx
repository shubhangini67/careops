"use client";

// P6-A1: persistent bottom-right chat bubble, accessible from every page.
// Shares state with the full /chat page via ChatSessionContext -- opening
// the bubble never starts a fresh conversation if one is already active,
// and "expand" hands off to the full page with identical history.

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { useAuth } from "@/context/AuthContext";
import { useChatSession } from "@/context/ChatSessionContext";
import VoiceRecordButton from "@/components/planning/VoiceRecordButton";

const HIDDEN_ON = ["/login", "/register"];
// /concierge has its own guest-facing chat (ConciergeChatArea) -- the
// operator-facing widget must never overlap it, even for a logged-in operator.
const HIDDEN_PREFIXES = ["/concierge"];

export default function FloatingChatWidget() {
  const { user, loading: authLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const {
    messages, busy, sessionId, sessionList, sessionListLoading,
    send, startNewSession, loadSession, deleteSession, refreshSessionList,
  } = useChatSession();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"chat" | "history">("chat");
  const [input, setInput] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  useEffect(() => {
    if (open && view === "history") refreshSessionList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, view]);

  if (HIDDEN_PREFIXES.some((p) => pathname.startsWith(p))) return null;
  if (authLoading || !user) return null;
  if (HIDDEN_ON.includes(pathname)) return null;
  if (pathname === "/chat") return null; // full page already showing the same conversation

  function handleSend() {
    if (!input.trim() || busy) return;
    send(input);
    setInput("");
  }

  async function handleLoadSession(id: number) {
    await loadSession(id);
    setView("chat");
  }

  async function handleDelete(id: number) {
    setConfirmDeleteId(null);
    try { await deleteSession(id); } catch { /* list just keeps the stale row on failure */ }
  }

  return (
    <div className="fixed bottom-5 right-5 z-50">
      {open && (
        <div className="mb-3 flex h-[480px] w-[340px] flex-col overflow-hidden rounded-2xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[var(--color-border-soft)] px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-gradient-to-b from-ember-500/30 to-ember-600/20 ring-1 ring-ember-400/25">
                <span className="text-[8px] font-bold text-[var(--color-accent)]">CO</span>
              </div>
              <span className="text-[11px] font-semibold text-[var(--color-text-primary)]">Policy Assistant</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setView(v => v === "chat" ? "history" : "chat")}
                title={view === "chat" ? "Past conversations" : "Back to chat"}
                className={`rounded-lg p-1.5 hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)] ${view === "history" ? "text-[var(--color-accent)]" : "text-[var(--color-text-faint)]"}`}
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h7" />
                </svg>
              </button>
              <button
                onClick={() => router.push("/chat")}
                title="Expand to full view"
                className="rounded-lg p-1.5 text-[var(--color-text-faint)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)]"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4" />
                </svg>
              </button>
              <button
                onClick={() => setOpen(false)}
                title="Close"
                className="rounded-lg p-1.5 text-[var(--color-text-faint)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)]"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {view === "history" ? (
            /* Past conversations */
            <div className="flex-1 overflow-y-auto py-2">
              <div className="flex items-center justify-between px-3 py-1.5">
                <span className="text-[9px] uppercase tracking-[0.2em] text-[var(--color-text-ghost)]">Conversations</span>
                <button
                  onClick={() => { startNewSession(); setView("chat"); }}
                  className="text-[10px] uppercase tracking-[0.1em] text-[var(--color-accent)] hover:opacity-70"
                >
                  + New
                </button>
              </div>
              {sessionListLoading && sessionList.length === 0 && (
                <p className="px-3 py-2 text-[11px] text-[var(--color-text-faint)]">Loading…</p>
              )}
              {!sessionListLoading && sessionList.length === 0 && (
                <p className="px-3 py-2 text-[11px] text-[var(--color-text-faint)]">No past conversations yet.</p>
              )}
              {sessionList.map((s) => (
                <div key={s.id} className="group relative flex items-center gap-1 px-1.5">
                  <button
                    onClick={() => handleLoadSession(s.id)}
                    className={`block flex-1 min-w-0 truncate rounded-lg px-2.5 py-2 text-left text-[12px] transition-colors ${
                      s.id === sessionId
                        ? "bg-[var(--color-accent-soft)] font-semibold text-[var(--color-accent)]"
                        : "text-[var(--color-text-faint)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)]"
                    }`}
                  >
                    {s.title || "Untitled conversation"}
                  </button>

                  {confirmDeleteId === s.id ? (
                    <div className="flex shrink-0 items-center gap-0.5">
                      <button onClick={() => handleDelete(s.id)} title="Confirm delete" className="rounded-md p-1 text-[var(--color-critical)] hover:bg-[var(--color-critical-soft)]">
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                      </button>
                      <button onClick={() => setConfirmDeleteId(null)} title="Cancel" className="rounded-md p-1 text-[var(--color-text-faint)] hover:bg-[var(--color-surface)]">
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmDeleteId(s.id)}
                      title="Delete conversation"
                      className="shrink-0 rounded-md p-1 text-[var(--color-text-ghost)] opacity-0 transition-opacity hover:bg-[var(--color-critical-soft)] hover:text-[var(--color-critical)] group-hover:opacity-100"
                    >
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-3 py-3">
                {messages.length === 0 && (
                  <p className="mt-8 text-center text-[11px] text-[var(--color-text-faint)]">
                    Ask me anything about hospital operations, policies, or past runs.
                  </p>
                )}
                <div className="space-y-3">
                  {messages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[85%] rounded-xl px-3 py-2 text-[12px] leading-relaxed ${
                        msg.role === "user"
                          ? "bg-[var(--color-accent-soft)] ring-1 ring-[var(--color-accent)]/25 text-[var(--color-text-primary)]"
                          : "bg-[var(--color-surface)] ring-1 ring-[var(--color-border-soft)] text-[var(--color-text-primary)]"
                      }`}>
                        {msg.role === "assistant" ? (
                          <div className="prose-chat prose-sm">
                            <ReactMarkdown>{msg.content || (msg.streaming ? "…" : "")}</ReactMarkdown>
                          </div>
                        ) : (
                          <span>{msg.content}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                <div ref={bottomRef} />
              </div>

              {/* Input */}
              <div className="border-t border-[var(--color-border-soft)] p-2.5">
                <div className="flex items-center gap-2 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface)] px-3 py-2">
                  <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleSend(); } }}
                    placeholder="Ask a quick question…"
                    disabled={busy}
                    className="w-full bg-transparent text-[12px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-ghost)] focus:outline-none disabled:opacity-40"
                  />
                  <VoiceRecordButton compact onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))} disabled={busy} />
                  <button
                    onClick={handleSend}
                    disabled={busy || !input.trim()}
                    className="shrink-0 text-[var(--color-accent)] disabled:opacity-25"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Bubble toggle */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex h-12 w-12 items-center justify-center rounded-full bg-ember-500 text-[var(--color-text-primary)] shadow-lg transition-transform hover:scale-105"
        title="Policy Assistant"
      >
        {open ? (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8-1.13 0-2.21-.184-3.2-.522L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )}
      </button>
    </div>
  );
}
