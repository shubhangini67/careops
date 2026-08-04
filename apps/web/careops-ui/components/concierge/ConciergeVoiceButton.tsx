"use client";

import { useEffect, useRef, useState } from "react";
import { transcribeConciergeAudio } from "@/lib/api";

const MAX_RECORDING_SECONDS = 60;

type RecordState = "idle" | "recording" | "transcribing" | "error";

export default function ConciergeVoiceButton({
  onTranscript,
  disabled,
}: {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}) {
  const [state, setState] = useState<RecordState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  useEffect(() => () => stopStream(), []);

  async function handleTranscribe(blob: Blob) {
    setState("transcribing");
    try {
      const text = await transcribeConciergeAudio(blob);
      onTranscript(text);
      setState("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not transcribe that, try typing instead.");
      setState("error");
    }
  }

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = () => {
        stopStream();
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        void handleTranscribe(blob);
      };

      recorderRef.current = recorder;
      recorder.start();
      setState("recording");
      setSeconds(0);
      timerRef.current = setInterval(() => {
        setSeconds((s) => {
          if (s + 1 >= MAX_RECORDING_SECONDS) recorder.stop();
          return s + 1;
        });
      }, 1000);
    } catch {
      setError("Microphone access denied, try typing instead.");
      setState("error");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
  }

  function handleClick() {
    if (disabled) return;
    if (state === "idle" || state === "error") void startRecording();
    else if (state === "recording") stopRecording();
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || state === "transcribing"}
      title={state === "recording" ? `Recording, ${seconds}s (tap to stop)` : state === "error" ? (error ?? "Try again") : "Speak instead"}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        state === "recording"
          ? "border-rose-500/40 bg-rose-500/10 text-rose-500"
          : state === "error"
          ? "border-rose-500/30 bg-transparent text-rose-500"
          : "border-[var(--color-border-default)] bg-[var(--color-surface-page)] text-[var(--color-text-faint)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
      }`}
    >
      {state === "recording" ? (
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-500 opacity-60" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose-500" />
        </span>
      ) : state === "transcribing" ? (
        <svg className="h-3.5 w-3.5 shrink-0 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
        </svg>
      )}
    </button>
  );
}
