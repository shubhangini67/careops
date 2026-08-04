"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ConciergeMessage } from "@/types/concierge";
import ToolResultCard from "@/components/concierge/ToolResultCard";
import ConciergeVoiceButton from "@/components/concierge/ConciergeVoiceButton";

const EXAMPLE_PROMPTS = [
  { icon: "🎂", q: "Plan my best friend's 25th birthday, 14 people, pizza lover, Rs.10k budget" },
  { icon: "💍", q: "Find a romantic rooftop restaurant for our anniversary this Saturday, 2 people" },
  { icon: "🎉", q: "We need Instamart supplies for a house party: cake, drinks, and decorations" },
  { icon: "💼", q: "Book a table for a corporate dinner, 8 people, tonight at 8pm" },
];

export default function ConciergeChatArea({
  messages,
  busy,
  headcount,
  onSend,
}: {
  messages: ConciergeMessage[];
  busy: boolean;
  headcount?: number | null;
  onSend: (text: string) => void;
}) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function submit(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    onSend(text.trim());
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(input); }
  }

  const empty = messages.length === 0;

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="relative flex-1 overflow-y-auto">
        <div className="pointer-events-none absolute inset-0 flex items-start justify-center overflow-hidden">
          <div className="mt-[-80px] h-[500px] w-[700px] rounded-full opacity-[0.06]"
            style={{ background: "radial-gradient(closest-side, #e6892a, transparent)" }} />
        </div>
        <div className="relative mx-auto max-w-2xl px-4 py-8">
          {empty && (
            <div className="pt-6 pb-4">
              <div className="text-center mb-10">
                <div className="inline-flex items-center gap-2 rounded-full border border-ember-500/20 bg-ember-500/[0.07] px-4 py-1.5 mb-5">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inset-0 animate-ping rounded-full bg-ember-400 opacity-60" />
                    <span className="relative rounded-full bg-ember-400" />
                  </span>
                  <span className="text-[10px] uppercase tracking-[0.26em] text-[var(--color-accent)]">Guest concierge</span>
                </div>
                <h1 className="text-[32px] font-semibold tracking-[-0.02em] text-[var(--color-text-primary)] leading-[1.05]">
                  What are we <span className="display-it text-[var(--color-accent)]">planning</span>?
                </h1>
                <p className="mt-3 text-[13px] leading-[1.7] text-[var(--color-text-faint)] max-w-sm mx-auto">
                  Tell me the occasion, headcount, and budget. I&apos;ll find venues, check slots, order food, and
                  handle Instamart supplies, powered by Swiggy.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {EXAMPLE_PROMPTS.map(({ icon, q }) => (
                  <button
                    key={q}
                    onClick={() => submit(q)}
                    className="card group flex items-start gap-3 px-4 py-3.5 text-left"
                  >
                    <span className="mt-0.5 shrink-0 text-[16px]">{icon}</span>
                    <p className="text-[13px] text-[var(--color-text-soft)] leading-snug group-hover:text-[var(--color-text-primary)] transition-colors">
                      {q}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-5">
            {messages.map((msg, i) => (
              <div key={i} className={`flex items-start gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl mt-0.5 ${
                  msg.role === "assistant"
                    ? "bg-gradient-to-b from-ember-500/30 to-ember-600/20 ring-1 ring-ember-400/25"
                    : "bg-[var(--color-accent-soft)] ring-1 ring-[var(--color-accent)]/30"
                }`}>
                  <span className="text-[9px] font-bold text-[var(--color-accent)]">{msg.role === "assistant" ? "CK" : "You"}</span>
                </div>

                <div className={`flex max-w-[85%] flex-col gap-2.5 ${msg.role === "user" ? "items-end" : "items-start"}`}>
                  {msg.role === "user" ? (
                    <div className="rounded-2xl rounded-tr-sm bg-[var(--color-accent-soft)] px-4 py-3 text-[13.5px] leading-relaxed text-[var(--color-text-primary)] ring-1 ring-[var(--color-accent)]/25 shadow-[0_1px_2px_rgba(20,15,5,0.05),0_10px_28px_-14px_rgba(20,15,5,0.22)]">
                      {msg.text}
                    </div>
                  ) : (
                    <>
                      {msg.toolResults.map((tr, ti) => (
                        <ToolResultCard key={ti} tool={tr.tool} data={tr.data} headcount={headcount} onQuickMessage={submit} />
                      ))}

                      {(msg.text || msg.streaming) && (
                        <div className="rounded-2xl rounded-tl-sm bg-[var(--color-surface-raised)] px-4 py-3 text-[13.5px] leading-relaxed text-[var(--color-text-primary)] ring-1 ring-[var(--color-border-default)] shadow-[0_1px_2px_rgba(20,15,5,0.05),0_10px_28px_-14px_rgba(20,15,5,0.22)]">
                          {!msg.text && msg.streaming && msg.statusText && (
                            <span className="flex items-center gap-2 text-[var(--color-text-faint)]">
                              <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[var(--color-accent)]" />
                              {msg.statusText}
                            </span>
                          )}
                          {!msg.text && msg.streaming && !msg.statusText && (
                            <span className="inline-flex gap-1.5 items-center py-0.5">
                              {[0, 150, 300].map((d) => (
                                <span key={d} className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: `${d}ms` }} />
                              ))}
                            </span>
                          )}
                          {msg.text && (
                            <div className="prose-chat">
                              <ReactMarkdown>{msg.text}</ReactMarkdown>
                              {msg.streaming && (
                                <span className="inline-block h-[14px] w-[2px] rounded-full bg-ember-400 animate-pulse ml-0.5 translate-y-[2px]" />
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div ref={bottomRef} className="h-4" />
        </div>
      </div>

      <div className="relative border-t border-[var(--color-border-default)] bg-white/95 px-4 pb-5 pt-4 backdrop-blur-md dark:bg-[var(--color-surface-page)]/95">
        <div className="mx-auto max-w-2xl">
          <div className="relative rounded-2xl border-2 border-[var(--color-border-default)] bg-[var(--color-surface-raised)] shadow-[0_2px_4px_rgba(20,15,5,0.06),0_16px_36px_-16px_rgba(20,15,5,0.28)] transition-all duration-200 focus-within:border-[var(--color-accent)] focus-within:shadow-[0_0_0_4px_rgba(255,82,0,0.10),0_16px_36px_-16px_rgba(20,15,5,0.28)]">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
              }}
              onKeyDown={handleKey}
              placeholder="Describe the event you're planning…"
              disabled={busy}
              className="w-full resize-none bg-transparent px-5 pt-4 pb-12 text-[14.5px] font-medium text-[var(--color-text-primary)] placeholder:font-normal placeholder:text-[var(--color-text-faint)] focus:outline-none disabled:opacity-40"
              style={{ maxHeight: "120px" }}
            />
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
                <ConciergeVoiceButton onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))} disabled={busy} />
                <button
                  onClick={() => submit(input)}
                  disabled={busy || !input.trim()}
                  className="flex items-center gap-1.5 rounded-xl bg-[var(--color-accent)] px-4 py-2 text-[12px] font-bold text-white shadow-[0_2px_8px_rgba(255,82,0,0.28)] transition-all hover:bg-[var(--color-hero-bg)] hover:shadow-[0_4px_14px_rgba(255,82,0,0.38)] disabled:bg-[var(--color-surface-sunken)] disabled:text-[var(--color-text-ghost)] disabled:shadow-none disabled:cursor-not-allowed"
                >
                  Send
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
