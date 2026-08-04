"use client";

import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import { FridayRushResponse } from "@/types/planning";

// Section 1, "Executive Situation" -- the hero of the page. Split layout:
// left is the AI-written narrative (situation_summary_node, one LLM call
// post-critic-approval), right is that same narrative's own "Key
// Takeaways" bullets, pulled out and rendered as small standalone cards
// so they read as scannable highlights rather than getting lost at the
// tail end of a paragraph block.
//
// Matches the app's established card language (CardHeader icon badge,
// .card-lift real resting elevation, SECTION_COLOR-style warm gradient
// accents -- see Market/Analytics) plus a rotating gradient border
// (globals.css .moving-border-card) as this page's one hero-only motion
// touch. Risk/caution phrases in the narrative (weather, shortages,
// negative sentiment, pricing pressure) are deterministically flagged in
// color -- not left to the LLM to remember to bold -- same spirit as
// HighlightSwiggy.tsx's brand-term highlighting elsewhere in this file
// tree, just pattern-matched against risk language instead of "Swiggy".
//
// The old fallback here used to carry its own internal/external conditions
// grid AND a Do Now/Before Service/Monitor action grid -- both now live
// permanently elsewhere on the page (SituationDrivers, ImmediateActionPlan)
// regardless of whether this LLM call succeeded, so this component's own
// fallback can stay simple: it only needs to cover the "no narrative text
// at all" case, not re-derive the same structured content a second time.

function splitNarrativeAndTakeaways(markdown: string): { narrative: string; takeaways: string[] } {
  const match = markdown.match(/\*\*Key Takeaways\*\*:?\s*\n([\s\S]*)$/i);
  if (!match || match.index === undefined) return { narrative: markdown, takeaways: [] };

  const narrative = markdown.slice(0, match.index).trim();
  const takeaways = match[1]
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => /^[-*•]/.test(l))
    .map((l) => l.replace(/^[-*•]\s*/, "").replace(/\*\*/g, "").trim())
    .filter(Boolean);

  return { narrative, takeaways };
}

// Sentinel-wraps risk/caution phrases in **bold** markdown before ReactMarkdown
// ever sees the text, using a marker character to tell "a flag I injected"
// apart from any bold the LLM wrote on its own -- the custom `strong`
// renderer below only recolors text carrying the marker, everything else
// still renders as plain bold.
const RISK_PATTERNS = /critically low|critical shortage(?:s)?|out of stock|(?:running|risk of )?overbook(?:ing|ed)?|\b\d{1,3}%\s*negative\b|understaffed|short-staffed/gi;
const CAUTION_PATTERNS = /heavy rain(?:fall)?|thunderstorms?|rainy|extreme heat|heatwave|higher[- ]priced|price[- ]sensitive|busier (?:than|night)|high demand/gi;

function flagRiskTerms(text: string): string {
  return text
    .replace(RISK_PATTERNS, (m) => `**⚑ROSE⚑${m}⚑**`)
    .replace(CAUTION_PATTERNS, (m) => `**⚑AMBER⚑${m}⚑**`);
}

const FLAG_TONE_CLASS: Record<string, string> = {
  ROSE: "text-rose-600 dark:text-rose-400",
  AMBER: "text-amber-600 dark:text-amber-500",
};

function flattenToString(node: React.ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(flattenToString).join("");
  return "";
}

const markdownComponents: Components = {
  strong({ children }) {
    const text = flattenToString(children);
    const match = text.match(/^⚑(ROSE|AMBER)⚑([\s\S]*)⚑$/);
    if (match) {
      return <mark className={`rounded bg-transparent px-0 font-semibold ${FLAG_TONE_CLASS[match[1]]}`}>{match[2]}</mark>;
    }
    return <strong>{children}</strong>;
  },
};

export default function PlanBriefing({ data }: { data: FridayRushResponse }) {
  const summary = data.situation_summary?.trim();

  return (
    <div className="@container stagger-1 card-lift moving-border-card">
      <div className="relative p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <span
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white shadow-sm"
            style={{ background: "linear-gradient(135deg, #FF5200, #FF5200cc)" }}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[16px] font-bold text-[var(--color-text-primary)]">Executive Situation</p>
              <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold" style={{ background: "rgba(255,82,0,0.1)", color: "var(--color-accent)" }}>
                <svg className="h-3 w-3 shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2l1.9 5.5L19 9.4l-5.1 1.9L12 17l-1.9-5.7L5 9.4l5.1-1.9L12 2z" />
                </svg>
                AI-generated · critic-reviewed
              </span>
            </div>
          </div>
        </div>

        {summary ? (
          <ExecutiveSituation summary={summary} />
        ) : (
          <p className="mt-4 text-[14px] leading-relaxed text-[var(--color-text-primary)]">
            Tonight&apos;s plan is ready. See the sections below for the full breakdown of demand, reservations,
            inventory, guest feedback, and menu guidance behind this plan.
          </p>
        )}
      </div>
    </div>
  );
}

function ExecutiveSituation({ summary }: { summary: string }) {
  const { narrative, takeaways } = splitNarrativeAndTakeaways(summary);
  const flaggedNarrative = flagRiskTerms(narrative);

  return (
    <div className="mt-5 grid grid-cols-1 gap-6 @4xl:grid-cols-[1fr_320px]">
      <div className="prose-chat min-w-0 text-[15px] leading-[1.75]">
        <ReactMarkdown components={markdownComponents}>{flaggedNarrative}</ReactMarkdown>
      </div>

      {takeaways.length > 0 && (
        <div
          className="min-w-0 rounded-2xl p-4"
          style={{ background: "linear-gradient(165deg, rgba(255,82,0,0.1), rgba(245,158,11,0.05))", border: "1px solid rgba(255,82,0,0.18)" }}
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--color-accent)" }}>Key takeaways</p>
          <div className="mt-2.5 space-y-2.5">
            {takeaways.map((t, i) => (
              <div key={i} className="card flex items-start gap-3 rounded-xl px-3.5 py-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-white shadow-sm" style={{ background: "linear-gradient(135deg, #10B981, #10B981cc)" }}>
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
                <p className="text-[12.5px] leading-relaxed text-[var(--color-text-primary)]">{t}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
