"use client";

// P6-A30 -- surfaces per-node cost/tokens/model/duration data that's always
// been captured in run metadata (node_traces/llm_usage, graph.py) but was
// never shown anywhere in the frontend before.

import { useState } from "react";
import { NodeTrace, PlanningRunMetadata } from "@/types/planning";

const NODE_LABELS: Record<string, string> = {
  supervisor_router: "Supervisor Router",
  capacity_forecast: "Capacity Forecast",
  fhir_operations: "FHIR Operations",
  policy_rag: "Policy RAG",
  resource_allocation: "Resource Allocation",
  aggregator: "Aggregator",
  safety_critic: "Safety Critic",
  human_approval_queue: "Human Approval Queue",
  ops_manager: "Ops Manager",
  demand_forecast: "Demand Forecast",
  qdrant_enrichment: "Memory Enrichment",
  reservation: "Reservation",
  complaint_intelligence: "Complaint Intelligence",
  inventory: "Inventory",
  market_intel: "Market Intel",
  dineout_manager: "Dineout Manager",
  menu_intelligence: "Menu Intelligence",
  critic: "Critic",
  replan_orchestrator: "Replan Orchestrator",
  final_assembler: "Final Assembler",
};

function fmtMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function fmtCost(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(5)}` : `$${usd.toFixed(3)}`;
}

function NodeRow({ trace }: { trace: NodeTrace }) {
  const [open, setOpen] = useState(false);
  // llm_usage is typed as always-present, but older/errored runs can omit it
  // entirely at runtime -- default defensively rather than crash the page.
  const llmUsage = trace.llm_usage ?? [];
  const models = Array.from(new Set(llmUsage.map(u => u.model)));
  const hasLlm = llmUsage.length > 0;

  return (
    <div className="border-b border-[var(--color-border-soft)] last:border-0">
      <button
        onClick={() => hasLlm && setOpen(v => !v)}
        className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left ${hasLlm ? "cursor-pointer hover:bg-[var(--color-surface-raised)]" : "cursor-default"}`}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${trace.error ? "bg-rose-400" : "bg-emerald-400"}`} />
          <span className="text-[13px] font-medium text-[var(--color-text-primary)] truncate">
            {NODE_LABELS[trace.node] ?? trace.node}
          </span>
          {models.length > 0 && (
            <span className="text-[11px] text-[var(--color-text-faint)] font-mono truncate">{models.join(", ")}</span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0 text-[11px] text-[var(--color-text-faint)] font-mono">
          <span>{fmtMs(trace.duration_ms)}</span>
          {trace.node_cost_usd > 0 && <span>{fmtCost(trace.node_cost_usd)}</span>}
          {hasLlm && (
            <svg className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>
      </button>
      {trace.error && (
        <p className="px-4 pb-2 text-[11px] text-rose-300/80">{trace.error}</p>
      )}
      {open && hasLlm && (
        <div className="px-4 pb-3 space-y-1.5">
          {llmUsage.map((u, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-[var(--color-surface-sunken)] px-3 py-1.5 text-[11px]">
              <span className="text-[var(--color-text-soft)]">{u.provider} · <span className="font-mono">{u.model}</span></span>
              <span className="font-mono text-[var(--color-text-faint)]">
                {u.prompt_tokens + u.completion_tokens} tok · {fmtCost(u.cost_usd)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ObservabilityStrip({ metadata }: { metadata: PlanningRunMetadata | null | undefined }) {
  const traces = metadata?.node_traces ?? [];
  if (traces.length === 0) return null;

  return (
    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] overflow-hidden">
      <div className="flex items-center justify-between border-b border-[var(--color-border-default)] px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold">Observability</h3>
          <p className="text-xs text-[var(--color-text-faint)]">Per-node status, timing, model, and cost for this run.</p>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono text-[var(--color-text-faint)]">
          {metadata?.total_duration_ms != null && <span>{fmtMs(metadata.total_duration_ms)} total</span>}
          {metadata?.total_tokens != null && <span>{metadata.total_tokens} tok</span>}
          {metadata?.total_cost_usd != null && <span>{fmtCost(metadata.total_cost_usd)}</span>}
        </div>
      </div>
      <div>
        {traces.map((t, i) => <NodeRow key={`${t.node}-${i}`} trace={t} />)}
      </div>
    </div>
  );
}
