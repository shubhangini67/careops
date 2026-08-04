import Image from "next/image";
import Link from "next/link";

const STATS = [
  { value: "7", label: "specialist agents working in parallel on hospital data" },
  { value: "<90s", label: "from pressing run to a safety-reviewed plan" },
  { value: "100%", label: "of sensitive actions require human approval" },
];

export default function AuthSplitLayout({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-[#070a12] lg:flex lg:flex-col lg:justify-between lg:p-14">
        <div className="dot-bg pointer-events-none absolute inset-0 opacity-40" />
        <div
          className="pointer-events-none absolute -top-32 -left-20 h-[520px] w-[520px] rounded-full"
          style={{ background: "radial-gradient(closest-side, rgba(14,165,233,0.22), transparent 72%)" }}
        />

        <Link href="/" className="relative flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center overflow-hidden rounded-xl bg-black ring-1 ring-white/10">
            <Image src="/ck-logo.png" alt="CareOps AI" width={32} height={32} className="h-8 w-8 object-contain" priority />
          </span>
          <div className="leading-tight">
            <div className="text-[15px] font-bold tracking-tight text-white">CareOps AI</div>
            <div className="text-[9px] uppercase tracking-[0.24em] text-sky-300/70">Hospital Operations</div>
          </div>
        </Link>

        <div className="relative max-w-md">
          <h2 className="text-[34px] leading-[1.08] tracking-[-0.02em] text-white">
            The operations<br /><span className="display-it text-sky-300">briefing</span> that runs itself.
          </h2>
          <p className="mt-4 text-[14px] leading-[1.7] text-white/55">
            Seven specialists read capacity forecasts, FHIR operations data, hospital policies, and supply levels — together, before every shift handoff.
          </p>

          <div className="mt-10 grid grid-cols-3 gap-6 border-t border-white/10 pt-6">
            {STATS.map(({ value, label }) => (
              <div key={label}>
                <div className="num-display text-[28px] leading-none text-white">{value}</div>
                <div className="mt-1.5 text-[11px] leading-snug text-white/45">{label}</div>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-[11px] text-white/30">
          Operational guidance only. Not medical diagnosis or treatment advice.
        </p>
      </div>

      <div className="flex flex-col justify-center px-6 py-12 sm:px-10 lg:px-14">
        <div className="mx-auto w-full max-w-md">
          <p className="text-[10px] uppercase tracking-[0.24em] text-[var(--color-accent)]">{eyebrow}</p>
          <h1 className="mt-2 text-[28px] font-semibold tracking-[-0.02em] text-[var(--color-text-primary)]">{title}</h1>
          <p className="mt-2 text-sm text-[var(--color-text-soft)]">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  );
}
