import Image from "next/image";
import Link from "next/link";
import HomeNav from "@/components/layout/HomeNav";
import Footer from "@/components/layout/Footer";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[var(--color-surface-page)] text-[var(--color-text-primary)]">
      <HomeNav />

      {/* Hero */}
      <section className="relative overflow-hidden grid-bg">
        <div
          className="pointer-events-none absolute -top-40 left-1/2 h-[640px] w-[1100px] -translate-x-1/2 rounded-full"
          style={{ background: "radial-gradient(closest-side, rgba(14,165,233,0.18), transparent 70%)" }}
        />

        <div className="relative mx-auto grid max-w-[1280px] grid-cols-1 gap-10 px-8 pb-24 pt-24 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full bg-sky-500/[0.08] px-3 py-1.5 ring-1 ring-sky-500/25">
              <span className="pulse flex h-1.5 w-1.5 rounded-full bg-sky-400" />
              <span className="text-[10px] uppercase tracking-[0.28em] text-sky-200">Hospital operations intelligence</span>
            </div>

            <h1 className="mt-7 text-[42px] leading-[0.96] tracking-[-0.025em] sm:text-[56px] md:text-[74px]">
              The operations<br />
              <span className="display-it text-sky-400">briefing</span> that<br />
              runs<span className="display-it"> itself.</span>
            </h1>

            <p className="mt-7 max-w-xl text-[17px] leading-[1.6] text-[var(--color-text-soft)]">
              CareOps AI reads capacity forecasts, FHIR operations data, hospital policies, and supply levels in parallel. Seven specialist agents build one safety-reviewed plan — with policy citations and a human approval queue before anything executes.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link href="/register" className="btn-primary inline-flex items-center gap-2 rounded-xl px-6 py-3.5 text-[15px] font-semibold">
                Start free trial
              </Link>
              <Link href="/login" className="inline-flex items-center gap-2 rounded-xl px-6 py-3.5 text-[15px] font-medium ring-1 ring-[var(--color-border-default)] transition-colors hover:ring-sky-400/40">
                Sign in to workspace
              </Link>
            </div>

            <div className="mt-12 grid max-w-xl grid-cols-3 gap-8 border-t border-[var(--color-border-default)] pt-7">
              <div>
                <div className="num-display text-[36px] leading-none">7<span className="text-2xl text-[var(--color-text-faint)]">×</span></div>
                <div className="mt-1.5 text-xs text-[var(--color-text-soft)]">specialist agents in parallel</div>
              </div>
              <div>
                <div className="num-display text-[36px] leading-none">&lt;90<span className="text-2xl text-[var(--color-text-faint)]">s</span></div>
                <div className="mt-1.5 text-xs text-[var(--color-text-soft)]">to a safety-reviewed plan</div>
              </div>
              <div>
                <div className="num-display text-[36px] leading-none">100<span className="text-2xl text-[var(--color-text-faint)]">%</span></div>
                <div className="mt-1.5 text-xs text-[var(--color-text-soft)]">human approval before execution</div>
              </div>
            </div>
          </div>

          <div className="xl:col-span-5">
            <div className="relative rounded-3xl bg-[var(--color-surface)] p-5 shadow-xl ring-1 ring-[var(--color-border-default)]">
              <div className="flex items-center justify-between border-b border-[var(--color-border-default)] pb-3">
                <span className="text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-faint)]">careops.ai/dashboard</span>
                <span className="font-mono text-[10px] text-[var(--color-text-faint)]">ed surge scenario</span>
              </div>
              <div className="mt-4 flex items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.22em] text-emerald-300">Safety verdict</div>
                  <div className="mt-1.5 text-2xl font-semibold">Plan approved</div>
                  <div className="mt-1 text-xs text-[var(--color-text-soft)]">Emergency Surge · 24h window · 12 beds available</div>
                </div>
                <div className="num-display text-5xl leading-none text-emerald-300">0.88</div>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-2">
                {[
                  { label: "ED forecast", value: "148", sub: "admissions" },
                  { label: "Bed load", value: "87%", sub: "ICU watch" },
                  { label: "Supply risk", value: "3", sub: "critical items" },
                ].map(({ label, value, sub }) => (
                  <div key={label} className="rounded-xl bg-[var(--color-surface-raised)] px-3 py-3 ring-1 ring-[var(--color-border-soft)]">
                    <div className="text-[9px] uppercase tracking-[0.18em] text-[var(--color-text-faint)]">{label}</div>
                    <div className="mt-1 num-display text-2xl">{value}</div>
                    <div className="text-[10px] text-[var(--color-text-faint)]">{sub}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid grid-cols-3 gap-1.5 sm:grid-cols-6">
                {["capacity ✓", "fhir ✓", "policy ✓", "resources ✓", "safety ✓", "queue ✓"].map((label) => (
                  <div key={label} className="rounded-md bg-[var(--color-surface-raised)] px-2 py-1.5 text-center text-[9px] uppercase tracking-wider text-emerald-300/90">
                    {label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-y border-[var(--color-border-soft)] bg-[var(--color-surface-raised)] px-8 py-28">
        <div className="mx-auto max-w-[1280px]">
          <div className="text-[10px] uppercase tracking-[0.22em] text-sky-400/80">How it works</div>
          <h2 className="mt-3 text-[40px] leading-[1.02] tracking-[-0.02em] md:text-[52px]">
            From scenario to <span className="display-it text-sky-400">plan</span> in 90 seconds.
          </h2>

          <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
            {[
              {
                num: "01",
                title: "Pick a hospital scenario",
                body: "Emergency surge, OPD peak load, ICU capacity watch, or supply shortage — or describe the situation in plain language.",
              },
              {
                num: "02",
                title: "Seven agents run in parallel",
                body: "Capacity forecast, FHIR operations, policy RAG, and resource allocation feed into a safety critic before you see the plan.",
              },
              {
                num: "03",
                title: "Review and approve",
                body: "Sensitive actions land in the approval queue. Policy citations are attached. Nothing executes without a human sign-off.",
              },
            ].map(({ num, title, body }) => (
              <article key={num} className="rounded-2xl bg-[var(--color-surface)] p-7 ring-1 ring-[var(--color-border-soft)]">
                <div className="num-display text-[80px] leading-none text-[var(--color-text-ghost)]">{num}</div>
                <h3 className="mt-4 text-2xl font-semibold">{title}</h3>
                <p className="mt-2.5 text-sm leading-[1.7] text-[var(--color-text-soft)]">{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="px-8 py-24">
        <div className="mx-auto max-w-[1280px]">
          <div className="mb-12 text-center">
            <h2 className="text-[38px] leading-[1.05] tracking-[-0.02em] md:text-[50px]">
              Built for <span className="display-it text-sky-400">hospital operators.</span>
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              { title: "Capacity Forecasting", desc: "Admission volume and bed pressure projections with transparent assumptions." },
              { title: "Policy RAG", desc: "Hospital SOPs and regulatory guidance retrieved with citations — not generic LLM advice." },
              { title: "FHIR Operations", desc: "Synthetic Patient, Encounter, Appointment, and Observation data for demo workflows." },
              { title: "Resource Allocation", desc: "Bed, staff shift, and supply planning across departments." },
              { title: "Safety Critic", desc: "Every plan scored for safety, feasibility, evidence, and actionability before delivery." },
              { title: "Approval Queue", desc: "Procurement and operational actions require explicit human approval." },
            ].map(({ title, desc }) => (
              <div key={title} className="rounded-2xl border border-[var(--color-border-soft)] p-6">
                <div className="text-[15px] font-semibold">{title}</div>
                <p className="mt-2 text-[13px] leading-[1.7] text-[var(--color-text-soft)]">{desc}</p>
              </div>
            ))}
          </div>
          <p className="mt-10 text-center text-[12px] text-[var(--color-text-faint)]">
            Operational guidance only. Not medical diagnosis or treatment advice. Synthetic data for demonstration.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="relative overflow-hidden px-8 py-32">
        <div className="relative mx-auto max-w-[920px] text-center">
          <h2 className="text-[48px] leading-[1.02] tracking-[-0.02em] md:text-[64px]">
            Brief your next shift<br /><span className="display-it text-sky-400">before</span> it starts.
          </h2>
          <p className="mx-auto mt-6 max-w-xl text-[16px] leading-[1.7] text-[var(--color-text-soft)]">
            Set up your hospital workspace in minutes. Seed data is included so you can run an ED surge scenario today.
          </p>
          <div className="mt-10">
            <Link href="/register" className="btn-primary inline-flex items-center gap-2 rounded-xl px-7 py-4 text-[15px] font-semibold">
              Get started free
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
