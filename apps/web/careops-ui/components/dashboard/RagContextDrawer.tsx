"use client";

import { useState } from "react";
import { RagContext } from "@/types/planning";

interface Props {
  ragContext: RagContext | null;
}

export default function RagContextDrawer({ ragContext }: Props) {
  const [open, setOpen] = useState(false);

  if (!ragContext) return null;

  const complaints = extractList(ragContext.complaints ?? ragContext);
  const sops = extractList(ragContext.sops);

  if (complaints.length === 0 && sops.length === 0) return null;

  return (
    <div className="card rounded-2xl overflow-hidden stagger-7">
      <button
        onClick={() => setOpen((value) => !value)}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-[var(--color-surface-raised)] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">🔍</span>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text-primary)]">Evidence Drawer</p>
            <p className="text-xs text-[var(--color-text-faint)]">
              {complaints.length} complaint{complaints.length !== 1 ? "s" : ""} retrieved
              {sops.length > 0 && `  -  ${sops.length} SOP${sops.length !== 1 ? "s" : ""}`}
            </p>
          </div>
        </div>
        <span className="text-[var(--color-text-faint)] text-lg">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-6 pb-6 space-y-5 border-t border-[var(--color-border-soft)]">
          {complaints.length > 0 && (
            <Section title="Past Complaints" items={complaints} accent="rose" />
          )}
          {sops.length > 0 && (
            <Section title="Relevant SOPs" items={sops} accent="blue" />
          )}
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  items,
  accent,
}: {
  title: string;
  items: string[];
  accent: "rose" | "blue";
}) {
  const border = accent === "rose" ? "border-rose-500/20" : "border-blue-500/20";
  const bg = accent === "rose" ? "bg-rose-500/10" : "bg-blue-500/10";
  const text = accent === "rose" ? "text-rose-200" : "text-blue-200";

  return (
    <div className="pt-4 first:pt-0">
      <p className="text-xs uppercase tracking-widest text-[var(--color-text-faint)] mb-3">
        {title}
      </p>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li
            key={`${title}-${index}`}
            className={`text-xs leading-relaxed px-3 py-3 rounded-xl border ${border} ${bg} ${text}`}
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function extractList(value: unknown): string[] {
  if (!value) return [];
  if (!Array.isArray(value)) return [];

  return value.map((item) => {
    if (typeof item === "string") return item;
    if (typeof item === "object" && item !== null) {
      const obj = item as Record<string, unknown>;
      return String(
        obj.text ?? obj.content ?? obj.complaint ?? obj.summary ?? JSON.stringify(item)
      );
    }
    return String(item);
  });
}
