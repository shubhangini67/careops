"use client";

// A proper cart-preview modal for "Check Instamart Price" -- upgraded from a
// small inline results box to a real multi-select experience (search, add,
// quantity steppers, running subtotal). Still entirely local/UI-only: real
// Instamart cart operations (update_cart/get_cart/checkout) stay blocked
// until Swiggy staging credentials land, so "Proceed to Checkout" is
// deliberately disabled here rather than pretending to place a real order.

import { useEffect, useState } from "react";
import { searchIngredient, type IngredientSearchResult } from "@/lib/api";
import { BagIcon, ChannelIcon, XIcon } from "./actionQueueMeta";

type Status = "loading" | "done" | "error" | "not_connected";
type CartLine = { result: IngredientSearchResult; qty: number };

export default function InstamartPriceModal({
  initialQuery, onClose,
}: {
  initialQuery: string;
  onClose: () => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState<Status>("loading");
  const [results, setResults] = useState<IngredientSearchResult[]>([]);
  const [cart, setCart] = useState<Record<string, CartLine>>({});

  const runSearch = async (q: string) => {
    if (!q.trim()) return;
    setStatus("loading");
    try {
      const res = await searchIngredient(q.trim());
      if (!res.swiggy_connected) { setStatus("not_connected"); return; }
      setResults(res.results);
      setStatus("done");
    } catch {
      setStatus("error");
    }
  };

  useEffect(() => {
    runSearch(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addToCart = (r: IngredientSearchResult) => {
    setCart((prev) => ({
      ...prev,
      [r.name]: { result: r, qty: (prev[r.name]?.qty ?? 0) + 1 },
    }));
  };

  const changeQty = (name: string, delta: number) => {
    setCart((prev) => {
      const existing = prev[name];
      if (!existing) return prev;
      const nextQty = existing.qty + delta;
      if (nextQty <= 0) {
        const next = { ...prev };
        delete next[name];
        return next;
      }
      return { ...prev, [name]: { ...existing, qty: nextQty } };
    });
  };

  const cartLines = Object.values(cart);
  const itemCount = cartLines.reduce((sum, line) => sum + line.qty, 0);
  const subtotal = cartLines.reduce((sum, line) => sum + line.result.price * line.qty, 0);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-[backdropIn_0.15s_ease_both]"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-[var(--color-surface-raised)] shadow-2xl animate-[modalIn_0.2s_ease-out_both]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border-soft)] bg-[var(--color-surface-raised)] px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white p-1.5 shadow-sm">
              <ChannelIcon channel="instamart" className="h-full w-full" />
            </div>
            <div>
              <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-accent)]">Live price check</p>
              <p className="mt-0.5 text-[15px] font-bold leading-tight text-[var(--color-text-primary)]">Check Supply Catalog Price</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-full p-1.5 text-[var(--color-text-faint)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-text-primary)]"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="flex gap-2 px-5 pt-4">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") runSearch(query); }}
            placeholder="Search an ingredient…"
            className="min-w-0 flex-1 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3 py-2 text-[13px] text-[var(--color-text-primary)] outline-none transition-shadow focus:ring-2 focus:ring-[var(--color-accent)]"
          />
          <button
            onClick={() => runSearch(query)}
            disabled={status === "loading"}
            className="btn-primary shrink-0 rounded-lg px-3.5 py-2 text-[12.5px] font-semibold disabled:opacity-50"
          >
            {status === "loading" ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="mt-3 flex-1 overflow-y-auto px-5">
          {status === "loading" && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--color-border-default)] border-t-[var(--color-accent)]" />
              <p className="text-[12px] text-[var(--color-text-faint)]">Checking supply catalog…</p>
            </div>
          )}
          {status === "not_connected" && (
            <p className="py-10 text-center text-[12px] text-[var(--color-text-faint)]">Connect the supply catalog integration to check live prices.</p>
          )}
          {status === "error" && (
            <p className="py-10 text-center text-[12px]" style={{ color: "var(--color-caution)" }}>
              Couldn&apos;t check supply price right now.
            </p>
          )}
          {status === "done" && results.length === 0 && (
            <p className="py-10 text-center text-[12px] text-[var(--color-text-faint)]">No matching supply items found right now.</p>
          )}
          {status === "done" && results.length > 0 && (
            <div className="space-y-2 pb-4">
              {results.map((r, i) => {
                const line = cart[r.name];
                return (
                  <div
                    key={i}
                    className="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] p-3 transition-colors hover:border-[var(--color-accent)]"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-semibold text-[var(--color-text-primary)]">{r.name}</p>
                      <p className="text-[11px] text-[var(--color-text-faint)]">
                        {r.category} · {r.in_stock ? "in stock" : "out of stock"}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2.5">
                      <span className="font-mono text-[13px] font-semibold text-[var(--color-text-primary)]">
                        ₹{r.price}/{r.unit}
                      </span>
                      {line ? (
                        <div className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-1.5 py-1">
                          <button
                            onClick={() => changeQty(r.name, -1)}
                            className="flex h-5 w-5 items-center justify-center rounded text-[13px] font-bold text-[var(--color-text-soft)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-text-primary)]"
                          >
                            −
                          </button>
                          <span className="w-4 text-center text-[12px] font-semibold text-[var(--color-text-primary)]">{line.qty}</span>
                          <button
                            onClick={() => changeQty(r.name, 1)}
                            className="flex h-5 w-5 items-center justify-center rounded text-[13px] font-bold text-[var(--color-text-soft)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-text-primary)]"
                          >
                            +
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => addToCart(r)}
                          disabled={!r.in_stock}
                          className="hero-instamart-btn inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11.5px] font-semibold text-[var(--color-text-primary)] disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <BagIcon className="h-3.5 w-3.5" />
                          Add
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="border-t border-[var(--color-border-soft)] bg-[var(--color-surface-sunken)] p-5">
          <div className="flex items-center justify-between text-[13px]">
            <span className="text-[var(--color-text-soft)]">{itemCount} item{itemCount !== 1 ? "s" : ""} in cart</span>
            <span className="font-mono font-bold text-[var(--color-text-primary)]">₹{subtotal.toFixed(0)}</span>
          </div>
          <button
            disabled
            title="Real procurement checkout requires human approval — this cart is a preview only."
            className="mt-2.5 w-full cursor-not-allowed rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-4 py-2.5 text-[12.5px] font-semibold text-[var(--color-text-faint)]"
          >
            Proceed to Checkout — coming soon
          </button>
        </div>
      </div>
    </div>
  );
}
