"use client";

import { ReactNode, useEffect } from "react";

interface Props {
  open: boolean;
  title: string;
  subtitle?: string;
  meta?: Array<{ label: string; value: string }>;
  highlights?: string[];
  onClose: () => void;
  children: ReactNode;
}

export default function DashboardDetailModal({
  open,
  title,
  subtitle,
  meta = [],
  highlights = [],
  onClose,
  children,
}: Props) {
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70]">
      <button
        aria-label="Close detail modal"
        className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-[backdropIn_0.15s_ease_both]"
        onClick={onClose}
      />
      <div className="absolute inset-x-4 top-6 bottom-6 xl:inset-x-16 2xl:inset-x-28">
        <div className="card h-full flex flex-col rounded-3xl overflow-hidden border-[var(--color-border-default)] shadow-2xl animate-[modalIn_0.2s_ease-out_both]">
          <div className="flex items-start justify-between gap-4 px-6 py-5 border-b border-[var(--color-border-soft)] bg-[var(--color-surface-raised)]">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-[var(--color-text-faint)]">
                Agent Detail
              </p>
              <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mt-1">{title}</h2>
              {subtitle && <p className="text-sm text-[var(--color-text-soft)] mt-1">{subtitle}</p>}
              {meta.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {meta.map((item) => (
                    <div
                      key={`${item.label}-${item.value}`}
                      className="rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3 py-1 text-[11px] font-mono text-[var(--color-text-soft)]"
                    >
                      <span className="text-[var(--color-text-faint)]">{item.label}</span>
                      <span className="mx-1 text-[var(--color-text-ghost)]"> - </span>
                      <span>{item.value}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={onClose}
              className="rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3 py-1.5 text-xs text-[var(--color-text-soft)] hover:bg-[var(--color-surface-sunken)] transition-colors"
            >
              close
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {highlights.length > 0 && (
              <div className="mb-6">
                <p className="text-xs uppercase tracking-[0.18em] text-[var(--color-text-faint)] mb-3">
                  Key Takeaways
                </p>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                  {highlights.map((item, index) => (
                    <div
                      key={`${item}-${index}`}
                      className="rounded-2xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-4 py-3 text-sm text-[var(--color-text-primary)]"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
