"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import VoiceRecordButton from "@/components/planning/VoiceRecordButton";

// A prominent "ask anything about this plan" bar, closing out the page.
// NOT position:fixed/sticky -- the app already has a global floating chat
// bubble on every page (components/chat/FloatingChatWidget.tsx, bottom-right,
// every route), so a second floating panel here would visually collide with
// it. This gets the same prominence via styling instead of overlay
// positioning: full-width, larger, its own card treatment as the page's
// last section.

const SUGGESTIONS = [
  "Why this recommendation?",
  "Alternative menu?",
  "Reduce waste?",
  "What if 20 more guests arrive?",
];

export default function AskAiBar() {
  const router = useRouter();
  const [question, setQuestion] = useState("");

  function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    router.push(`/chat?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <div className="card rounded-2xl p-5 sm:p-6">
      <div className="flex items-center gap-2">
        <svg className="h-4 w-4 shrink-0 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">Ask the AI about this plan</p>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); submit(question); }}
        className="mt-3 flex gap-2"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about this plan…"
          className="flex-1 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3.5 py-2.5 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-ghost)] focus:outline-none focus:ring-2 focus:ring-ember-500/50"
        />
        <VoiceRecordButton onTranscript={(text) => setQuestion((prev) => (prev ? `${prev} ${text}` : text))} />
        <button type="submit" className="btn-primary shrink-0 rounded-lg px-4 py-2 text-xs font-semibold">Send</button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => submit(s)}
            className="rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3 py-1.5 text-[11.5px] text-[var(--color-text-soft)] transition-colors hover:border-ember-500/30 hover:text-[var(--color-text-primary)]"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
