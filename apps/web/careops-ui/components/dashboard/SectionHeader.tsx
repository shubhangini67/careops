"use client";

export default function SectionHeader({
  label,
  description,
  tone = "default",
  isOpen,
  onToggle,
  cards,
}: {
  label: string;
  description: string;
  tone?: "ember" | "cyan" | "rose" | "emerald" | "amber" | "default";
  isOpen?: boolean;
  onToggle?: () => void;
  cards?: string[];
}) {
  const toneClass: Record<
    NonNullable<Parameters<typeof SectionHeader>[0]["tone"]>,
    { bar: string; label: string }
  > = {
    ember: { bar: "bg-ember-400/70", label: "text-[var(--color-accent)]/80" },
    cyan: { bar: "bg-cyan-300/70", label: "text-cyan-200/80" },
    rose: { bar: "bg-rose-400/70", label: "text-rose-200/80" },
    emerald: { bar: "bg-emerald-300/70", label: "text-emerald-200/80" },
    amber: { bar: "bg-amber-300/70", label: "text-amber-200/80" },
    default: { bar: "bg-[var(--color-surface-raised)]", label: "text-[var(--color-text-soft)]" },
  };
  const toneStyle = toneClass[tone] ?? toneClass.default;

  return (
    <div
      className={`px-1 flex items-center gap-3 ${onToggle ? "cursor-pointer select-none group" : ""}`}
      onClick={onToggle}
    >
      <div className={`h-10 w-1 rounded-full flex-shrink-0 ${toneStyle.bar}`} />
      <div className="flex-1 min-w-0">
        <p className={`text-xs uppercase tracking-[0.18em] ${toneStyle.label}`}>
          {label}
        </p>
        <p className="mt-1 text-sm text-[var(--color-text-soft)]">{description}</p>
        {!isOpen && cards && cards.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {cards.map((card) => (
              <span
                key={card}
                className="inline-flex items-center rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-2.5 py-0.5 text-[10px] tracking-wide text-[var(--color-text-faint)]"
              >
                {card}
              </span>
            ))}
          </div>
        )}
      </div>
      {onToggle !== undefined && (
        <svg
          className={`flex-shrink-0 h-4 w-4 text-[var(--color-text-faint)] transition-transform duration-200 group-hover:text-[var(--color-text-soft)] ${isOpen ? "rotate-0" : "-rotate-90"}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      )}
    </div>
  );
}
