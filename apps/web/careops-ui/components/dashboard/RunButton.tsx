// components/dashboard/RunButton.tsx
"use client";

import Spinner from "@/components/ui/Spinner";

interface Props {
  onRun:    () => void;
  onReset?: () => void;
  loading:  boolean;
  hasData:  boolean;
}

export default function RunButton({ onRun, onReset, loading, hasData }: Props) {
  return (
    <div className="flex items-center gap-3">
      <button
        onClick={() => onRun()}
        disabled={loading}
        className="inline-flex items-center gap-2 px-5 py-2.5
          bg-ember-600 hover:bg-ember-500
          disabled:opacity-50 disabled:cursor-not-allowed
          text-[var(--color-text-primary)] text-sm font-semibold rounded-xl
          shadow-glow-ember
          transition-all duration-200
          border border-ember-500/50
        "
      >
        {loading ? (
          <>
            <Spinner size={15} />
            <span className="text-xs tracking-wide">Running pipeline...</span>
          </>
        ) : (
          <>
            <span></span>
            <span>Run Friday Rush</span>
          </>
        )}
      </button>

      {hasData && !loading && onReset && (
        <button
          onClick={() => onReset()}
          className="text-xs text-[var(--color-text-ghost)] hover:text-[var(--color-text-soft)] transition-colors"
        >
          reset
        </button>
      )}
    </div>
  );
}