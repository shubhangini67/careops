"use client";

import type { ReactNode } from "react";

// Shared page-masthead style: bold sans title + a short accent underline,
// no eyebrow label, no full-width border. Rolled out from the Action Center
// redesign (P6-A31) to the other secondary pages so headings read as one
// consistent system instead of each page inventing its own.
export default function PageHeading({
  title,
  description,
  icon,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start gap-3">
      {icon}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="text-[28px] font-bold text-[var(--color-text-primary)]">{title}</h1>
          {action}
        </div>
        <div className="mt-2 h-1 w-12 rounded-full" style={{ background: "var(--color-accent)" }} />
        {description && (
          <p className="mt-3 max-w-2xl text-sm text-[var(--color-text-soft)]">{description}</p>
        )}
      </div>
    </header>
  );
}
