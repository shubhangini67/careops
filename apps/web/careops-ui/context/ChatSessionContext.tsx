"use client";

// P6-A1: chat history/session state lifted above page-level so the floating
// widget and the full /chat page share one source of truth -- switching
// between them never loses context, and either surface can browse/resume
// any past conversation thread.

import { createContext, useCallback, useContext, useRef, useState } from "react";
import { getAuthToken } from "@/lib/auth-cookies";
import { getChatSessions, getChatSession, deleteChatSession, ChatSessionSummary } from "@/lib/api";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

interface ChatSessionCtx {
  messages: ChatMessage[];
  busy: boolean;
  sessionId: number | null;
  sessionList: ChatSessionSummary[];
  sessionListLoading: boolean;
  send: (question: string) => Promise<void>;
  startNewSession: () => void;
  loadSession: (id: number) => Promise<void>;
  deleteSession: (id: number) => Promise<void>;
  refreshSessionList: () => Promise<void>;
}

const Context = createContext<ChatSessionCtx | null>(null);

export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages]       = useState<ChatMessage[]>([]);
  const [busy, setBusy]               = useState(false);
  const [sessionId, setSessionId]     = useState<number | null>(null);
  const [sessionList, setSessionList] = useState<ChatSessionSummary[]>([]);
  const [sessionListLoading, setSessionListLoading] = useState(false);
  const sessionIdRef = useRef<number | null>(null);

  const refreshSessionList = useCallback(async () => {
    setSessionListLoading(true);
    try {
      const list = await getChatSessions();
      setSessionList(list);
    } catch {
      // non-fatal -- history list just stays stale/empty
    } finally {
      setSessionListLoading(false);
    }
  }, []);

  const startNewSession = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    sessionIdRef.current = null;
  }, []);

  const loadSession = useCallback(async (id: number) => {
    const detail = await getChatSession(id);
    setMessages(detail.messages.map(m => ({ role: m.role, content: m.content })));
    setSessionId(detail.id);
    sessionIdRef.current = detail.id;
  }, []);

  const deleteSession = useCallback(async (id: number) => {
    await deleteChatSession(id);
    setSessionList(prev => prev.filter(s => s.id !== id));
    // Deleting the conversation currently open -- clear it back to the
    // empty state rather than leaving a now-nonexistent session loaded.
    if (sessionIdRef.current === id) {
      setMessages([]);
      setSessionId(null);
      sessionIdRef.current = null;
    }
  }, []);

  const send = useCallback(async (question: string) => {
    if (!question.trim() || busy) return;
    const q = question.trim();
    setBusy(true);

    const history = messages.map(m => ({ role: m.role, content: m.content }));
    setMessages(prev => [
      ...prev,
      { role: "user", content: q },
      { role: "assistant", content: "", streaming: true },
    ]);

    try {
      const token = getAuthToken();
      const res = await fetch(`${BASE_URL}/api/v1/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question: q, history, session_id: sessionIdRef.current }),
      });

      if (!res.ok || !res.body) throw new Error(`API error ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          try {
            const payload = JSON.parse(line.slice(5).trim());
            if (payload.session_id && sessionIdRef.current === null) {
              sessionIdRef.current = payload.session_id;
              setSessionId(payload.session_id);
            }
            if (payload.token) {
              setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant")
                  next[next.length - 1] = { ...last, content: last.content + payload.token };
                return next;
              });
            }
            // Backend errors (e.g. LLM provider rate limits) previously just
            // broke this loop with no visible trace -- the bubble went from
            // "thinking" straight to permanently blank once streaming=false
            // was set in the finally block below, reading as a stuck/dead
            // chatbot rather than a real, explainable failure.
            if (payload.error) {
              setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant" && !last.content)
                  next[next.length - 1] = { ...last, content: `Something went wrong: ${payload.error}` };
                return next;
              });
            }
            if (payload.done || payload.error) break;
          } catch { /* skip malformed */ }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: `Something went wrong. ${err instanceof Error ? err.message : ""}`,
        };
        return next;
      });
    } finally {
      setMessages(prev => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") next[next.length - 1] = { ...last, streaming: false };
        return next;
      });
      setBusy(false);
      refreshSessionList();
    }
  }, [messages, busy, refreshSessionList]);

  return (
    <Context.Provider value={{
      messages, busy, sessionId, sessionList, sessionListLoading,
      send, startNewSession, loadSession, deleteSession, refreshSessionList,
    }}>
      {children}
    </Context.Provider>
  );
}

export function useChatSession(): ChatSessionCtx {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useChatSession must be used within a ChatSessionProvider");
  return ctx;
}
