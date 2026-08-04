"use client";

// Compact per-card pill showing what Swiggy-sourced signal shaped this agent's
// recommendation (e.g. "3 Instamart prices live", "area tonight: HIGH").
// Shared between AgentCard.tsx (dashboard live view) and the /runs history
// page's AgentOutputCard — both need the same "insights also came from
// Swiggy" attribution, not two divergent implementations.
export default function SwiggySignalBadge({ signal }: { signal: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-[#fc8019]/25 bg-[#fc8019]/10 px-2.5 py-1">
      <img src="/swiggy-logo.png" alt="Swiggy" className="h-3 w-3 rounded-sm object-contain" />
      <span className="font-mono text-[10px] text-[#fc8019]/90 truncate max-w-[140px]">{signal}</span>
    </div>
  );
}
