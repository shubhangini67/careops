"use client";

import { useEffect, useState } from "react";
import VoiceRecordButton from "@/components/planning/VoiceRecordButton";
import { composeLiveScenario, deriveScenarioProfile, RestaurantProfile } from "@/lib/api";
import { PlanTriggerHandler, ScenarioProfile } from "@/types/planning";

interface Props {
  open: boolean;
  onClose: () => void;
  onRun: PlanTriggerHandler;
  activeProfile: RestaurantProfile | null;
}

// Optional tags folded straight into the free-text sent to
// deriveScenarioProfile (e.g. "Holiday. Low Stock.\n\nWe're hosting a
// wedding tonight.") -- no separate backend concept, just words the AI reads
// the same way it reads typed or spoken text.
const CONTEXT_CHIPS = [
  "ED Surge", "Staff Shortage", "Supply Shortage", "Flu Season",
  "Equipment Down", "Mass Casualty", "Holiday Volume", "ICU Full",
];

const PLANNING_WITH = ["Capacity Forecast", "FHIR Data", "Hospital Policies", "Staff & Beds", "Supply Levels", "Safety Critic"];

function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function tomorrowISO(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function buildCombinedText(chips: string[], freeText: string): string {
  const parts: string[] = [];
  if (chips.length > 0) parts.push(chips.join(". ") + ".");
  if (freeText.trim()) parts.push(freeText.trim());
  return parts.join("\n\n");
}

// The whole trigger surface, redesigned around one principle: the dashboard/
// planning page already show what the AI knows (live signals, restaurant
// profile, the specialist grid) -- this modal is only for what it doesn't
// know yet. Every path (a preset-style tag, typed text, or a voice
// transcript) folds into the exact same derive-a-profile-and-run call; there
// is no separate "mode" to pick between other than *when* to plan for.
export default function PlanShiftModal({ open, onClose, onRun, activeProfile }: Props) {
  const [planFor, setPlanFor] = useState<"next_service" | "specific_date">("next_service");
  const [specificDate, setSpecificDate] = useState(tomorrowISO());
  const [selectedChips, setSelectedChips] = useState<string[]>([]);
  const [freeText, setFreeText] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Every reopen starts clean -- a stale voice transcript or chip selection
  // from a previous run should never silently carry into the next one.
  useEffect(() => {
    if (!open) return;
    setPlanFor("next_service");
    setSpecificDate(tomorrowISO());
    setSelectedChips([]);
    setFreeText("");
    setGenerateError(null);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  function toggleChip(chip: string) {
    setSelectedChips((prev) => prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip]);
  }

  function handleTranscript(text: string) {
    setFreeText((prev) => (prev.trim() ? `${prev.trim()} ${text}` : text));
  }

  const hasContext = selectedChips.length > 0 || freeText.trim().length > 0;
  const canGenerate = planFor === "next_service" || Boolean(specificDate);

  async function handleGenerate() {
    if (!canGenerate || generating) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const combined = buildCombinedText(selectedChips, freeText);
      const effectiveDate = planFor === "next_service" ? todayISO() : specificDate;

      let profile: ScenarioProfile;
      if (combined.trim().length >= 3) {
        profile = await deriveScenarioProfile(combined);
      } else {
        const composition = await composeLiveScenario(effectiveDate);
        profile = composition.profile;
      }

      onRun(effectiveDate, activeProfile?.name ?? undefined, activeProfile?.id ?? undefined, profile, profile.id);
      onClose();
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "Couldn't generate a plan — try again.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[70]">
      <button
        aria-label="Close plan-your-shift dialog"
        className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-[backdropIn_0.15s_ease_both]"
        onClick={onClose}
      />
      <div className="absolute inset-x-4 top-8 bottom-8 mx-auto max-w-2xl xl:top-14 xl:bottom-14">
        <div className="card flex h-full flex-col overflow-hidden rounded-3xl border-[var(--color-border-default)] shadow-2xl animate-[modalIn_0.2s_ease-out_both]">
          <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border-soft)] bg-[var(--color-surface-raised)] px-6 py-5">
            <div>
              <p className="text-[10.5px] font-bold uppercase tracking-[0.18em] text-[var(--color-accent)]">Plan your next scenario</p>
              <h2 className="display mt-1 text-2xl text-[var(--color-text-primary)]">Tell the AI what it doesn&apos;t know yet</h2>
              <p className="mt-1 text-[13px] text-[var(--color-text-soft)]">Everything else — capacity, FHIR data, policies, and supply levels — it already has.</p>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3 py-1.5 text-xs text-[var(--color-text-soft)] transition-colors hover:bg-[var(--color-surface-sunken)]"
            >
              close
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6">
            {/* ── Plan for ── */}
            <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-faint)]">Plan for</p>
            <div className="mt-2 grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => setPlanFor("next_service")}
                className={`rounded-xl border px-4 py-3 text-left transition-all ${
                  planFor === "next_service"
                    ? "border-ember-400/40 bg-ember-500/10"
                    : "border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] hover:bg-[var(--color-surface-raised)]"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <p className={`text-[13.5px] font-bold ${planFor === "next_service" ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}`}>Next 24 Hours</p>
                  <span className="rounded-full px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide text-[var(--color-accent)]" style={{ background: "var(--color-accent-soft)" }}>Recommended</span>
                </div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--color-text-faint)]">The AI picks the right hospital scenario for today&apos;s operational window.</p>
              </button>
              <button
                type="button"
                onClick={() => setPlanFor("specific_date")}
                className={`rounded-xl border px-4 py-3 text-left transition-all ${
                  planFor === "specific_date"
                    ? "border-ember-400/40 bg-ember-500/10"
                    : "border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] hover:bg-[var(--color-surface-raised)]"
                }`}
              >
                <p className={`text-[13.5px] font-bold ${planFor === "specific_date" ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}`}>Specific Date</p>
                {planFor === "specific_date" ? (
                  <input
                    type="date"
                    value={specificDate}
                    min={todayISO()}
                    onChange={(e) => setSpecificDate(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="mono mt-1.5 w-full rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-2 py-1 text-[12px] text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-ember-500/50"
                  />
                ) : (
                  <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--color-text-faint)]">Plan ahead for a particular day.</p>
                )}
              </button>
            </div>

            {/* ── Planning context ── */}
            <div className="mt-6">
              <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-faint)]">Planning context <span className="normal-case font-medium text-[var(--color-text-ghost)]">(optional)</span></p>
              <div className="mt-2 flex flex-wrap gap-2">
                {CONTEXT_CHIPS.map((chip) => {
                  const active = selectedChips.includes(chip);
                  return (
                    <button
                      key={chip}
                      type="button"
                      onClick={() => toggleChip(chip)}
                      className={`rounded-full border px-3 py-1.5 text-[12px] font-semibold transition-colors ${
                        active
                          ? "border-ember-400/40 bg-ember-500/15 text-[var(--color-accent)]"
                          : "border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] text-[var(--color-text-soft)] hover:bg-[var(--color-surface-raised)]"
                      }`}
                    >
                      {chip}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* ── Tell the AI anything else ── */}
            <div className="mt-6">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-faint)]">Tell the AI anything else <span className="normal-case font-medium text-[var(--color-text-ghost)]">(optional)</span></p>
                <VoiceRecordButton onTranscript={handleTranscript} disabled={generating} />
              </div>
              <textarea
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
                placeholder="e.g. ED is at 95% capacity, two nurses called out, and surgical gloves are below reorder threshold…"
                rows={4}
                className="mt-2 w-full resize-none rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3.5 py-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-ghost)] focus:outline-none focus:ring-2 focus:ring-ember-500/50 focus:border-ember-500/60"
              />
            </div>

            {/* ── Planning with (trust strip) ── */}
            <div className="mt-6 border-t border-[var(--color-border-soft)] pt-5">
              <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-faint)]">Planning with</p>
              <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-2">
                {PLANNING_WITH.map((item) => (
                  <span key={item} className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-text-soft)]">
                    <svg className="h-3.5 w-3.5 shrink-0 text-[var(--color-good)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                    {item}
                  </span>
                ))}
                <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium transition-colors ${hasContext ? "text-[var(--color-accent)]" : "text-[var(--color-text-ghost)]"}`}>
                  <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  Your Instructions
                </span>
              </div>
            </div>

            {generateError && (
              <p className="mt-4 text-[12px] text-rose-400">{generateError}</p>
            )}

            <button
              type="button"
              onClick={handleGenerate}
              disabled={!canGenerate || generating}
              className="btn-primary mt-6 flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3 text-[14px] font-semibold transition-transform hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generating ? (
                <>
                  <svg className="h-4 w-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Composing your plan…
                </>
              ) : (
                <>
                  <svg className="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2l1.5 5.5L19 9l-5.5 1.5L12 16l-1.5-5.5L5 9l5.5-1.5z" /></svg>
                  Generate Plan
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
