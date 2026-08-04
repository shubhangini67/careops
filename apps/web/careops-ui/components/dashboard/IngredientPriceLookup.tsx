"use client";

import { useState } from "react";
import { searchIngredient, IngredientSearchResult } from "@/lib/api";

type Status = "idle" | "loading" | "success" | "error" | "not_connected";

function ProduceCrateIllustration() {
  // Purely decorative -- an abstract crate-of-produce illustration (no
  // fabricated photography), echoing the reference mockup's corner visual.
  return (
    <svg viewBox="0 0 200 120" className="h-24 w-40 shrink-0" aria-hidden="true">
      <ellipse cx="100" cy="108" rx="90" ry="8" fill="var(--color-border-soft)" />
      <path d="M20 60 L180 60 L165 108 L35 108 Z" fill="#d9a066" stroke="#b9824f" strokeWidth="2" />
      <path d="M20 60 L35 108 M180 60 L165 108 M65 60 L58 108 M135 60 L142 108" stroke="#b9824f" strokeWidth="2" />
      <circle cx="55" cy="48" r="22" fill="#f97316" />
      <circle cx="95" cy="40" r="18" fill="#ef4444" />
      <circle cx="130" cy="50" r="20" fill="#84cc16" />
      <circle cx="155" cy="34" r="13" fill="#a855f7" />
      <rect x="88" y="14" width="6" height="16" rx="3" fill="#4d7c0f" transform="rotate(-15 91 22)" />
      <circle cx="35" cy="38" r="12" fill="#facc15" />
    </svg>
  );
}

export default function IngredientPriceLookup() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [results, setResults] = useState<IngredientSearchResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function runSearch() {
    const trimmed = query.trim();
    if (!trimmed) return;
    setStatus("loading");
    setError(null);
    try {
      const res = await searchIngredient(trimmed);
      if (!res.swiggy_connected) {
        setStatus("not_connected");
        return;
      }
      setResults(res.results);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setStatus("error");
    }
  }

  return (
    <div className="card card-lift p-6">
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex min-w-[220px] items-center gap-3">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm"
            style={{ background: "linear-gradient(135deg, #C2410C, #C2410Ccc)" }}
          >
            <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <circle cx="11" cy="11" r="7" /><path strokeLinecap="round" d="M21 21l-4.35-4.35" />
            </svg>
          </span>
          <div>
            <p className="text-[14px] font-bold text-[var(--color-text-primary)]">Ingredient Price Lookup</p>
            <p className="mt-0.5 text-[10.5px] text-[var(--color-text-faint)]">via Swiggy MCP</p>
          </div>
        </div>

        <div className="flex flex-1 min-w-[260px] items-center gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="e.g. paneer, tomatoes, cream"
            className="flex-1 rounded-lg border border-[var(--color-border-soft)] bg-[var(--color-surface-page)] px-4 py-2.5 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-ghost)]"
          />
          <button
            onClick={runSearch}
            disabled={status === "loading" || !query.trim()}
            className="shrink-0 rounded-lg bg-[var(--color-accent)] px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {status === "loading" ? "…" : "Search"}
          </button>
        </div>

        <p className="hidden max-w-[220px] text-xs text-[var(--color-text-faint)] lg:block">
          Search any ingredient for its live Instamart price
        </p>

        <div className="ml-auto hidden sm:block">
          <ProduceCrateIllustration />
        </div>
      </div>

      <div className="mt-3">
        {status === "not_connected" && (
          <p className="text-xs text-[var(--color-text-ghost)] italic">Connect Swiggy to search live Instamart prices.</p>
        )}
        {status === "error" && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
        {status === "success" && results.length === 0 && (
          <p className="text-xs text-[var(--color-text-ghost)] italic">No products found for &quot;{query}&quot;.</p>
        )}
        {status === "success" && results.length > 0 && (
          <div className="mt-2 space-y-1.5 border-t border-[var(--color-border-soft)] pt-3">
            {results.map((r, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-[var(--color-border-soft)] bg-[var(--color-surface-sunken)] px-3 py-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${r.in_stock ? "bg-emerald-400" : "bg-blue-300"}`} />
                  <span className="text-xs text-[var(--color-text-soft)] truncate">{r.name}</span>
                </div>
                <span className="font-mono text-xs font-semibold text-[var(--color-text-primary)] shrink-0">₹{r.price}/{r.unit}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
