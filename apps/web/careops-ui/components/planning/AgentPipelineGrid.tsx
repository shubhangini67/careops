"use client";

import { AGENT_PIPELINE, AGENT_TONE_CLASS, type AgentCapability } from "./agentPipeline";

interface Props {
  // 8 specialist cards, 3 per row. 8 doesn't divide evenly by 3 (3+3+2), so
  // the columns===3 grid runs on a 6-col track instead with each card
  // spanning 2 (first 6, 3-per-row) or 3 (last 2, evenly filling the final
  // row instead of leaving a gap) -- see gridSpanClass below.
  columns?: 2 | 3;
}

// One specialist, as a proper feature card -- not a flowchart node. No step
// number, no "runs after X" chrome: an owner cares what this finds or
// protects for them, not where it sits in a graph. A small status dot
// (top-right) marks live-data agents -- orange for Swiggy-sourced, green for
// everything else -- instead of a text badge, so the claim registers without
// spending card width on it.
function SpecialistCard({ agent }: { agent: AgentCapability }) {
  const tone = AGENT_TONE_CLASS[agent.tone];
  const dotColor = agent.swiggy ? "#fc8019" : agent.live ? "#fc8019" : "var(--color-good)";
  return (
    <div className="card group flex h-full flex-col gap-1.5 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-white transition-transform duration-200 group-hover:scale-110 group-hover:rotate-6"
            style={{ background: tone.fill }}
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.9}>
              <path strokeLinecap="round" strokeLinejoin="round" d={agent.iconPath} />
            </svg>
          </span>
          <div className="flex min-w-0 items-center gap-1">
            <p className="truncate text-[13.5px] font-bold text-[var(--color-text-primary)]">{agent.label}</p>
            <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide" style={{ background: tone.bg, color: tone.text }}>Agent</span>
          </div>
        </div>
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60" style={{ background: dotColor }} />
          <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: dotColor }} />
        </span>
      </div>
      <p title={agent.capability} className="line-clamp-2 text-[11.5px] font-medium leading-snug text-[var(--color-text-primary)]">{agent.capability}</p>
      <ul className="mt-auto flex flex-col gap-1 pt-1.5">
        {agent.capabilities.slice(0, 2).map((item) => (
          <li key={item} className="flex items-center gap-1.5 text-[11px] font-medium leading-snug text-[var(--color-text-soft)]">
            <svg className="h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke={tone.text} strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

// The "meet your planning team" visual for the /planning idle state --
// deliberately NOT a pipeline flowchart: no arrows, no step numbers, no
// "running in parallel" callout. An end user doesn't care about execution
// topology,
// they care what each specialist actually finds or protects for them. The
// "Your Final Plan" result used to render as its own banner below the grid;
// dropped once PlanningIdleState's left-column "What You'll Get" checklist
// started covering the same "here's what a run produces" job.
// A 6-col track (not 3), so the last row can be deliberately asymmetric
// instead of 8 identical rectangles: the first 6 cards span 2 each (3-per-
// row, same as before), then Menu Strategy spans 4 (wide) and Critic spans 2
// (narrow) -- one intentional break in an otherwise uniform grid, instead of
// evenly splitting the last row and looking auto-generated.
function gridSpanClass(index: number, total: number): string {
  if (index === total - 2) return "xl:col-span-4"; // Menu Strategy
  if (index === total - 1) return "xl:col-span-2"; // Critic
  return "xl:col-span-2";
}

export default function AgentPipelineGrid({ columns = 3 }: Props) {
  return (
    <div className={`grid grid-cols-1 gap-x-2.5 gap-y-4 sm:grid-cols-2 ${columns === 3 ? "xl:grid-cols-6" : ""}`}>
      {AGENT_PIPELINE.map((agent, i) => (
        <div key={agent.label} className={columns === 3 ? gridSpanClass(i, AGENT_PIPELINE.length) : undefined}>
          <SpecialistCard agent={agent} />
        </div>
      ))}
    </div>
  );
}
