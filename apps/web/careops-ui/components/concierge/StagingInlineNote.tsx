"use client";

export function StagingInlineNote({ text }: { text: string }) {
  return (
    <p className="mt-2 flex items-start gap-1.5 rounded-lg bg-amber-400/10 px-2.5 py-1.5 text-[10.5px] leading-snug text-amber-700 dark:text-amber-400">
      <span className="mt-[1px] shrink-0">⏳</span>
      <span>{text}</span>
    </p>
  );
}
