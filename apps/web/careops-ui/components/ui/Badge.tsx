// components/ui/Badge.tsx

type Variant = "ready" | "needs_review" | "blocked" | "unknown" |
               "approved" | "rejected" | "revision" |
               "pending" | "executed" | "expired" | "failed";

const STYLES: Record<Variant, string> = {
  ready:        "pill pill-ready",
  approved:     "pill pill-ready",
  executed:     "pill pill-ready",
  needs_review: "pill pill-review",
  revision:     "pill pill-review",
  pending:      "pill pill-review",
  blocked:      "pill pill-blocked",
  rejected:     "pill pill-blocked",
  expired:      "pill pill-blocked",
  failed:       "pill pill-blocked",
  unknown:      "pill pill-unknown",
};

const DOTS: Record<Variant, string> = {
  ready:        "bg-emerald-400",
  approved:     "bg-emerald-400",
  executed:     "bg-emerald-400",
  needs_review: "bg-amber-400",
  revision:     "bg-amber-400",
  pending:      "bg-amber-400",
  blocked:      "bg-rose-400",
  rejected:     "bg-rose-400",
  expired:      "bg-rose-400",
  failed:       "bg-rose-400",
  unknown:      "bg-slate-400",
};

const LABELS: Record<Variant, string> = {
  ready:        "Ready",
  approved:     "Approved",
  executed:     "Executed",
  needs_review: "Needs Review",
  revision:     "Revision",
  pending:      "Pending",
  blocked:      "Blocked",
  rejected:     "Rejected",
  expired:      "Expired",
  failed:       "Failed",
  unknown:      "Unknown",
};

export default function Badge({ variant }: { variant: Variant }) {
  const style = STYLES[variant] ?? STYLES.unknown;
  const dot   = DOTS[variant]   ?? DOTS.unknown;
  const label = LABELS[variant] ?? variant;

  return (
    <span className={style}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot} ${variant === "blocked" ? "animate-pulse" : ""}`} />
      {label}
    </span>
  );
}