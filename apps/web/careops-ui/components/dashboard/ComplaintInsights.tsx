"use client";

interface ComplaintIssue {
  issue: string;
  frequency?: string;
  recommendation?: string;
  priority?: "high" | "medium" | "low";
}

interface ComplaintData {
  total_feedback?: number;
  sentiment_breakdown?: {
    negative?: number;
    positive?: number;
    neutral?: number;
    negative_pct?: number;
  };
  unique_complaints?: string[];
}

interface ComplaintRecommendation {
  issues?: ComplaintIssue[];
  overall_summary?: string;
  action_items?: string[];
}

interface NormalizedComplaint {
  summary: ComplaintData;
  recommendation: ComplaintRecommendation;
}

interface Props {
  complaint: Record<string, unknown> | null;
  compact?: boolean;
}

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function takeStrings(value: unknown, limit = 3): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .slice(0, limit);
}

function normalizeComplaint(raw: Record<string, unknown> | null): NormalizedComplaint | null {
  if (!raw) return null;

  const summarySource = asObject(raw.data) ?? raw;
  const recSource = asObject(raw.recommendation) ?? raw;

  const sentiment = asObject(summarySource.sentiment_breakdown) ?? asObject(raw.sentiment_breakdown);
  const totalFeedback = summarySource.total_feedback ?? raw.total_feedback;

  const issues =
    (Array.isArray(recSource.issues) ? (recSource.issues as ComplaintIssue[]) : null) ??
    (Array.isArray(raw.issues) ? (raw.issues as ComplaintIssue[]) : []);

  return {
    summary: {
      total_feedback: typeof totalFeedback === "number" ? totalFeedback : Number(totalFeedback ?? 0),
      sentiment_breakdown: sentiment
        ? {
            negative: typeof sentiment.negative === "number" ? sentiment.negative : Number(sentiment.negative ?? 0),
            positive: typeof sentiment.positive === "number" ? sentiment.positive : Number(sentiment.positive ?? 0),
            neutral: typeof sentiment.neutral === "number" ? sentiment.neutral : Number(sentiment.neutral ?? 0),
            negative_pct:
              typeof sentiment.negative_pct === "number"
                ? sentiment.negative_pct
                : Number(sentiment.negative_pct ?? 0),
          }
        : undefined,
      unique_complaints: Array.isArray(summarySource.unique_complaints)
        ? (summarySource.unique_complaints as string[])
        : Array.isArray(raw.unique_complaints)
          ? (raw.unique_complaints as string[])
          : undefined,
    },
    recommendation: {
      issues,
      overall_summary:
        typeof recSource.overall_summary === "string"
          ? String(recSource.overall_summary)
          : typeof raw.overall_summary === "string"
            ? String(raw.overall_summary)
            : undefined,
      action_items: Array.isArray(recSource.action_items)
        ? (recSource.action_items as string[])
        : Array.isArray(raw.action_items)
          ? (raw.action_items as string[])
          : undefined,
    },
  };
}

function priorityBadge(priority?: string) {
  if (!priority) return "border-[var(--color-border-default)] bg-[var(--color-surface-raised)] text-[var(--color-text-soft)]";
  const key = String(priority).toLowerCase();
  if (key === "high") return "border-rose-500/20 bg-rose-500/10 text-rose-200";
  if (key === "medium") return "border-amber-500/20 bg-amber-500/10 text-amber-200";
  if (key === "low") return "border-emerald-500/20 bg-emerald-500/10 text-emerald-200";
  return "border-[var(--color-border-default)] bg-[var(--color-surface-raised)] text-[var(--color-text-soft)]";
}

export function ComplaintInsightsBody({
  complaint,
  compact = false,
}: Props) {
  const normalized = normalizeComplaint(complaint);
  if (!normalized) return null;

  const issues = Array.isArray(normalized.recommendation.issues)
    ? normalized.recommendation.issues
    : [];
  const actionItems = Array.isArray(normalized.recommendation.action_items)
    ? normalized.recommendation.action_items
    : [];

  const sentiment = normalized.summary.sentiment_breakdown;
  const negativePct =
    sentiment && typeof sentiment.negative_pct === "number"
      ? sentiment.negative_pct
      : undefined;

  const shownIssues = compact ? issues.slice(0, 2) : issues.slice(0, 4);
  const shownActions = compact ? actionItems.slice(0, 2) : actionItems.slice(0, 5);

  return (
    <div className={compact ? "space-y-4" : "space-y-5"}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-faint)]">
        <span>{normalized.summary.total_feedback ?? 0} feedback</span>
        {typeof negativePct === "number" && (
          <>
            <span> - </span>
            <span className={negativePct >= 25 ? "text-rose-300" : "text-[var(--color-text-soft)]"}>
              negative: {negativePct}%
            </span>
          </>
        )}
        {issues.length > 0 && (
          <>
            <span> - </span>
            <span>{issues.length} issues</span>
          </>
        )}
      </div>

      {normalized.recommendation.overall_summary && (
        <div className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-4 py-3">
          <p className="text-xs uppercase tracking-widest text-[var(--color-text-faint)] mb-2">
            Summary
          </p>
          <p className={`text-sm text-[var(--color-text-primary)] leading-relaxed ${compact ? "line-clamp-3" : ""}`}>
            {normalized.recommendation.overall_summary}
          </p>
        </div>
      )}

      {shownIssues.length > 0 && (
        <div className={compact ? "space-y-2" : "space-y-3"}>
          <p className="text-xs uppercase tracking-widest text-[var(--color-text-ghost)]">
            Top Issues
          </p>
          <div className="grid grid-cols-1 gap-2">
            {shownIssues.map((issue, index) => (
              <div
                key={`${issue.issue}-${index}`}
                className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-4 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-[var(--color-text-primary)]">{issue.issue}</p>
                  {issue.priority && (
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] ${priorityBadge(issue.priority)}`}
                    >
                      {issue.priority}
                    </span>
                  )}
                </div>
                {!compact && issue.recommendation && (
                  <p className="mt-2 text-sm text-[var(--color-text-soft)] leading-relaxed">
                    {issue.recommendation}
                  </p>
                )}
              </div>
            ))}
          </div>
          {compact && issues.length > shownIssues.length && (
            <p className="text-xs text-[var(--color-text-faint)]">
              {issues.length - shownIssues.length} more issues in details.
            </p>
          )}
        </div>
      )}

      {shownActions.length > 0 && (
        <div className={compact ? "space-y-2" : "space-y-3"}>
          <p className="text-xs uppercase tracking-widest text-[var(--color-text-ghost)]">
            Action Items
          </p>
          <ul className="space-y-1.5">
            {shownActions.map((item, index) => (
              <li
                key={`action-${index}`}
                className="rounded-lg border border-[var(--color-border-soft)] bg-[var(--color-surface-sunken)] px-3 py-2 text-xs text-[var(--color-text-primary)]"
              >
                {item}
              </li>
            ))}
          </ul>
          {compact && actionItems.length > shownActions.length && (
            <p className="text-xs text-[var(--color-text-faint)]">
              {actionItems.length - shownActions.length} more actions in details.
            </p>
          )}
        </div>
      )}

      {!compact && normalized.summary.unique_complaints && normalized.summary.unique_complaints.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-widest text-[var(--color-text-ghost)]">
            Example Complaints
          </p>
          <ul className="space-y-1.5">
            {takeStrings(normalized.summary.unique_complaints, 5).map((text, index) => (
              <li
                key={`complaint-${index}`}
                className="rounded-lg border border-[var(--color-border-soft)] bg-[var(--color-surface-raised)] px-3 py-2 text-xs text-[var(--color-text-soft)]"
              >
                {text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ComplaintInsights({ complaint }: { complaint: Record<string, unknown> | null }) {
  return <ComplaintInsightsBody complaint={complaint} compact={false} />;
}

