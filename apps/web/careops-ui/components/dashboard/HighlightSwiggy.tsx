"use client";

// Wraps every "Swiggy" occurrence in recommendation text with the brand badge
// styling so market-intelligence-grounded insights are visually distinct from
// internal-data insights, per CLAUDE.md's Swiggy branding rules.
export default function HighlightSwiggy({ text }: { text: string }) {
  if (!text) return <>{text}</>;

  const parts = text.split(/(swiggy)/gi);
  if (parts.length === 1) return <>{text}</>;

  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === "swiggy" ? (
          <span key={i} className="font-semibold text-orange-300">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}
