// Small formatting helpers shared between Dashboard and Planning idle
// states -- both render "last run"-style timestamps and verdict badges
// the same way.

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export const VERDICT_TONE: Record<string, { bg: string; text: string; label: string }> = {
  approved: { bg: "var(--color-good-soft)",      text: "var(--color-good)",       label: "Approved" },
  revision: { bg: "var(--color-caution-soft)",   text: "var(--color-caution)",    label: "Revised" },
  rejected: { bg: "var(--color-critical-soft)",  text: "var(--color-critical)",   label: "Rejected" },
  unknown:  { bg: "var(--color-surface-sunken)", text: "var(--color-text-faint)", label: "Unknown" },
};
