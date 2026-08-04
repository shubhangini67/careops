"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { getOrgSettings, updateOrgSettings, OrgSettings } from "@/lib/api";
import { useRouter } from "next/navigation";
import PageHeading from "@/components/ui/PageHeading";

// Same visual system as the /data tabs: icon-badge section headers, neutral
// ring + shadow cards (not the orange-tinted .card border, which reads too
// "wireframe-y" for a dense grid of small elements), distinct color per
// section. Restaurant/Planning Thresholds now sit side by side instead of
// stacked in one narrow column.

function IconStorefront(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M13 21v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4M3 9h18M4 9l1.5-5h13L20 9M4 9v9a2 2 0 002 2h12a2 2 0 002-2V9" /></svg>;
}
function IconGauge(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9 9 0 100-18 9 9 0 000 18z" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 12l3.5-3.5M8 12a4 4 0 118 0" /></svg>;
}

interface FieldDef {
  key: keyof OrgSettings;
  label: string;
  type: "text" | "number";
  hint: string;
  min?: number;
  max?: number;
}

const SECTION_COLOR = {
  facility: "#0ea5e9",
  thresholds: "#0891B2",
} as const;

const FIELD_CONFIG: { section: string; icon: React.ReactNode; color: string; fields: FieldDef[] }[] = [
  {
    section: "Hospital Facility",
    icon: <IconStorefront className="h-4 w-4" />,
    color: SECTION_COLOR.facility,
    fields: [
      { key: "capacity",     label: "Licensed Bed Capacity",  type: "number", min: 1,             hint: "Total operational beds across monitored departments" },
      { key: "cuisine_type", label: "Facility Type",          type: "text",                       hint: "e.g. Acute Care, Multi-specialty, Community Hospital" },
      { key: "peak_hours",   label: "Peak Operations Window", type: "text",                       hint: "When demand is typically highest, e.g. 08:00-20:00" },
      { key: "timezone",     label: "Timezone",               type: "text",                       hint: "Your facility's local timezone, e.g. Asia/Kolkata" },
    ],
  },
  {
    section: "Planning Thresholds",
    icon: <IconGauge className="h-4 w-4" />,
    color: SECTION_COLOR.thresholds,
    fields: [
      { key: "critic_threshold",        label: "Plan Approval Score",  type: "number", min: 0, max: 1,   hint: "Minimum safety score to auto-approve a plan (0 to 1, default 0.7)" },
      { key: "low_stock_threshold_pct", label: "Low Supply Warning at", type: "number", min: 0, max: 100, hint: "Alert when a supply item drops below this % of reorder level" },
      { key: "overstock_threshold_pct", label: "Overstock Warning at", type: "number", min: 0, max: 100, hint: "Alert when a supply item exceeds this % of normal stock" },
    ],
  },
];

function validateSettings(s: OrgSettings): string | null {
  if (s.capacity < 1)
    return "Bed capacity must be at least 1.";
  if (s.critic_threshold < 0 || s.critic_threshold > 1)
    return "Critic threshold must be between 0.0 and 1.0.";
  if (s.low_stock_threshold_pct < 0 || s.low_stock_threshold_pct > 100)
    return "Low stock alert % must be between 0 and 100.";
  if (s.overstock_threshold_pct < 0 || s.overstock_threshold_pct > 100)
    return "Overstock alert % must be between 0 and 100.";
  return null;
}

const INPUT_CLS = "w-full bg-[var(--color-surface-sunken)] border border-[var(--color-border-default)] rounded-lg px-3 py-2 text-[var(--color-text-primary)] text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-ember-500/50 focus:border-ember-500/60 transition-colors";

export default function SettingsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [saving, setSaving]     = useState(false);
  const [saved, setSaved]       = useState(false);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    if (user && user.role !== "owner") { router.push("/"); return; }
    getOrgSettings().then(r => setSettings(r.settings)).catch(e => setError(e.message));
  }, [user, router]);

  function handleChange(key: keyof OrgSettings, value: string) {
    if (!settings) return;
    const prev = settings[key];
    const parsed = typeof prev === "number" ? parseFloat(value) || 0 : value;
    setSettings({ ...settings, [key]: parsed });
    setSaved(false);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!settings) return;
    const validationErr = validateSettings(settings);
    if (validationErr) { setError(validationErr); return; }
    setSaving(true); setError(null); setSaved(false);
    try {
      const res = await updateOrgSettings(settings);
      setSettings(res.settings);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  if (!settings) return (
    <div className="min-h-screen page-canvas flex items-center justify-center">
      <p className="text-[var(--color-text-faint)] text-sm">{error ?? "Loading settings..."}</p>
    </div>
  );

  return (
    <main className="min-h-screen page-canvas px-5 py-6 text-[var(--color-text-primary)] xl:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <PageHeading title="Workspace Settings" description="Hospital facility profile and planning thresholds for CareOps AI." />

        {/* Org/role line and Save button share one row -- the button lives
            next to "Casa Mia - owner", not stranded below both cards. It's
            wired to the form below via the form="" attribute since it's
            rendered outside that <form> element here. */}
        <div className="-mt-2 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-[var(--color-text-soft)]">
            {user?.org_name ?? ""}{user?.org_name && user?.role ? "  -  " : ""}{user?.role ?? ""}
          </p>
          <button
            type="submit"
            form="settings-form"
            disabled={saving}
            className="btn-primary rounded-lg px-6 py-2 text-sm font-semibold transition-opacity disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>

        <form id="settings-form" onSubmit={handleSave} className="space-y-6">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {FIELD_CONFIG.map(({ section, icon, color, fields }) => (
              <div key={section} className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-[var(--color-border-soft)] dark:bg-[var(--color-surface-raised)] md:p-6">
                <div className="mb-5 flex items-center gap-3">
                  <span
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white shadow-sm"
                    style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
                  >
                    {icon}
                  </span>
                  <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">{section}</h2>
                </div>
                <div className="space-y-4">
                  {fields.map(({ key, label, type, hint, min, max }) => (
                    <div key={key}>
                      <label className="block text-sm text-[var(--color-text-soft)] mb-1.5">{label}</label>
                      <input
                        type={type}
                        min={min}
                        max={max}
                        step={type === "number" ? "any" : undefined}
                        value={settings[key]}
                        onChange={e => handleChange(key, e.target.value)}
                        className={INPUT_CLS}
                      />
                      <p className="text-xs text-[var(--color-text-ghost)] mt-1">{hint}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {error && (
            <div className="text-sm text-rose-600 dark:text-rose-300 bg-rose-500/10 rounded-xl px-4 py-3 ring-1 ring-rose-500/20">
              {error}
            </div>
          )}

          {saved && (
            <div className="text-sm text-emerald-600 dark:text-emerald-300 bg-emerald-500/10 rounded-xl px-4 py-3 ring-1 ring-emerald-500/20">
              Settings saved successfully.
            </div>
          )}
        </form>
      </div>
    </main>
  );
}
