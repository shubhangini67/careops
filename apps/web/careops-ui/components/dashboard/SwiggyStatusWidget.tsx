"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { ConnectorStatus, getConnectorsStatus, triggerSwiggySync } from "@/lib/api";

export default function SwiggyStatusWidget() {
  const [connector, setConnector] = useState<ConnectorStatus | null>(null);
  const [syncing,   setSyncing]   = useState(false);
  const [syncOk,    setSyncOk]    = useState(false);

  useEffect(() => {
    getConnectorsStatus()
      .then((d) => setConnector(d.connectors.find((c) => c.type === "swiggy") ?? null))
      .catch(() => { /* non-blocking */ });
  }, []);

  async function handleQuickSync() {
    if (syncing) return;
    setSyncing(true);
    setSyncOk(false);
    try {
      await triggerSwiggySync();
      setSyncOk(true);
      const d = await getConnectorsStatus();
      setConnector(d.connectors.find((c) => c.type === "swiggy") ?? null);
    } catch { /* ignore */ } finally {
      setSyncing(false);
    }
  }

  if (!connector) return null;

  const connected = connector.connected;
  const fresh     = connector.last_sync_at
    ? (Date.now() - new Date(connector.last_sync_at).getTime()) < 2 * 3_600_000
    : false;

  return (
    <div className="card card-lift flex shrink-0 items-center gap-3 px-5 py-3.5">
      <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent)]">
        <Image src="/swiggy-logo.png" alt="Swiggy" width={22} height={22} className="h-[22px] w-[22px] object-contain" />
        <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-[var(--color-surface-raised)] ${connected ? (fresh ? "bg-emerald-400" : "bg-amber-400") : "bg-blue-300"}`} />
      </div>
      <div>
        <p className="text-sm font-semibold text-[var(--color-text-primary)]">{connected ? "Connected to Swiggy" : "Swiggy not connected"}</p>
        <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-faint)]">via Swiggy MCP</p>
      </div>

      {connected && (
        <button
          onClick={handleQuickSync}
          disabled={syncing}
          title="Sync Swiggy data now"
          className="ml-2 flex shrink-0 items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {syncing ? (
            <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : syncOk ? (
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          ) : null}
          {syncing ? "Syncing" : syncOk ? "Synced" : "Sync"}
        </button>
      )}
    </div>
  );
}
