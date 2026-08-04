"use client";

import { useState } from "react";
import { PlanningScenarioOption } from "@/types/planning";

interface Props {
  onRun:    (date?: string) => void;
  loading:  boolean;
  scenario?: PlanningScenarioOption;
  compact?: boolean;
}

function getUpcomingDates(
  weekday: number,
  scenarioLabel: string,
  count = 6
): { label: string; value: string }[] {
  const dates = [];
  const today = new Date();
  const day = today.getDay();
  const daysAhead = (weekday - ((day + 6) % 7) + 7) % 7;

  const nextDate = new Date(today);
  nextDate.setDate(today.getDate() + (daysAhead === 0 ? 7 : daysAhead));

  for (let index = 0; index < count; index++) {
    const date = new Date(nextDate);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const dayOfMonth = String(date.getDate()).padStart(2, "0");
    const value = `${year}-${month}-${dayOfMonth}`;
    const label =
      index === 0
        ? `Next ${scenarioLabel}  -  ${value}`
        : index === 1
        ? `${scenarioLabel} +1 week  -  ${value}`
        : value;

    dates.push({ label, value });
    nextDate.setDate(nextDate.getDate() + 7);
  }

  return dates;
}

export default function DatePicker({ onRun, loading, scenario, compact = false }: Props) {
  const scenarioLabel = scenario?.label ?? "Friday Rush";
  const weekday       = scenario?.default_weekday ?? 4;
  const dates         = getUpcomingDates(weekday, scenarioLabel, 6);
  const [selected, setSelected]   = useState<string>("");
  const [custom, setCustom]       = useState(false);
  const [customDate, setCustomDate] = useState("");

  const handleRun = () => {
    const date = custom ? customDate : selected;
    onRun(date || undefined);
  };

  const selectCls = "flex-1 min-w-0 text-xs font-mono border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] text-[var(--color-text-soft)] rounded-xl px-3 py-2.5 focus:outline-none focus:border-ember-500/50 disabled:opacity-50 transition-colors hover:border-[var(--color-border-default)]";

  return (
    <div className={compact ? "flex items-center gap-2 flex-wrap" : "space-y-3"}>
      {/* Preset / custom toggle */}
      <div className="inline-flex items-center rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] p-0.5 shrink-0">
        <button
          onClick={() => { setCustom(false); setCustomDate(""); }}
          disabled={loading}
          className={`px-3 py-1 rounded-full text-[11px] transition-colors ${
            !custom ? "bg-ember-500/20 text-ember-200" : "text-[var(--color-text-faint)] hover:text-[var(--color-text-soft)]"
          }`}
        >
          presets
        </button>
        <button
          onClick={() => { setCustom(true); setSelected(""); }}
          disabled={loading}
          className={`px-3 py-1 rounded-full text-[11px] transition-colors ${
            custom ? "bg-ember-500/20 text-ember-200" : "text-[var(--color-text-faint)] hover:text-[var(--color-text-soft)]"
          }`}
        >
          custom
        </button>
      </div>

      {/* Date input + run button */}
      <div className="flex gap-2 flex-1 min-w-0">
        {!custom ? (
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={loading}
            className={selectCls}
          >
            <option value="">{scenarioLabel} -- default date</option>
            {dates.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        ) : (
          <input
            type="date"
            value={customDate}
            onChange={(e) => setCustomDate(e.target.value)}
            disabled={loading}
            className={selectCls}
          />
        )}

        <button
          onClick={handleRun}
          disabled={loading || (custom && !customDate)}
          className={`inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl
            border border-ember-400/30 bg-gradient-to-b from-ember-500 to-ember-600
            font-semibold tracking-wide text-[var(--color-text-primary)]
            shadow-[0_4px_16px_rgba(230,137,42,0.35)]
            transition-all duration-200
            hover:-translate-y-0.5 hover:from-ember-400 hover:to-ember-600 hover:shadow-[0_6px_22px_rgba(230,137,42,0.45)]
            active:translate-y-0 active:shadow-[0_2px_8px_rgba(230,137,42,0.25)]
            disabled:cursor-not-allowed disabled:translate-y-0 disabled:opacity-40 disabled:shadow-none
            ${compact ? "px-4 py-2.5 text-xs" : "px-6 py-2.5 text-sm"}
          `}
        >
          {loading ? (
            <>
              <svg className="h-3.5 w-3.5 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Running...
            </>
          ) : (
            <>
              <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {compact ? "Re-run" : "Generate Plan"}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
