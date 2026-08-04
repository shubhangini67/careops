import Link from "next/link";

const FOOTER_LINKS = [
  {
    heading: "Product",
    links: [
      { label: "Dashboard",   href: "/dashboard" },
      { label: "Run History", href: "/runs" },
      { label: "Ask AI",      href: "/chat" },
      { label: "Data Health", href: "/data-health" },
      { label: "Changelog",   href: "#" },
    ],
  },
  {
    heading: "Resources",
    links: [
      { label: "Documentation", href: "#" },
      { label: "API Reference",  href: "#" },
      { label: "System Status",  href: "#" },
      { label: "Releases",       href: "#" },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "About",   href: "#" },
      { label: "Blog",    href: "#" },
      { label: "Careers", href: "#" },
      { label: "Contact", href: "#" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { label: "Privacy Policy",    href: "#" },
      { label: "Terms of Service",  href: "#" },
      { label: "Cookie Policy",     href: "#" },
      { label: "Security",          href: "#" },
    ],
  },
];

const SOCIALS = [
  {
    label: "GitHub",
    href: "#",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
        <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
      </svg>
    ),
  },
  {
    label: "X / Twitter",
    href: "#",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
      </svg>
    ),
  },
  {
    label: "LinkedIn",
    href: "#",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
      </svg>
    ),
  },
];

export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-[var(--color-border-default)] bg-[var(--color-surface-page)]">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-12 lg:py-16">

        {/* Top row — brand + link columns */}
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-2 lg:grid-cols-5">

          {/* Brand column */}
          <div className="col-span-2 sm:col-span-2 lg:col-span-1">
            <div className="flex items-center gap-2.5">
              {/* wordmark dot */}
              <span className="inline-block h-2 w-2 rounded-full bg-ember-400" />
              <span className="text-[15px] font-bold tracking-tight text-[var(--color-text-primary)]">CareOps AI</span>
            </div>
            <p className="mt-3 text-[12px] leading-relaxed text-[var(--color-text-faint)] max-w-[200px]">
              Agentic hospital operations and policy copilot for capacity, staffing, and supply planning.
            </p>

            {/* Socials */}
            <div className="mt-5 flex items-center gap-3">
              {SOCIALS.map((s) => (
                <a
                  key={s.label}
                  href={s.href}
                  aria-label={s.label}
                  className="text-[var(--color-text-ghost)] transition-colors hover:text-[var(--color-text-soft)]"
                >
                  {s.icon}
                </a>
              ))}
            </div>
          </div>

          {/* Link columns */}
          {FOOTER_LINKS.map((col) => (
            <div key={col.heading}>
              <p className="text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-faint)] mb-3">
                {col.heading}
              </p>
              <ul className="space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="text-[13px] text-[var(--color-text-faint)] transition-colors hover:text-[var(--color-text-primary)]"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-[var(--color-border-soft)] pt-6 sm:flex-row">
          <p className="text-[11px] text-[var(--color-text-ghost)]">
            © {year} CareOps AI. All rights reserved.
          </p>
          <div className="flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] text-[var(--color-text-ghost)]">All systems operational</span>
          </div>
        </div>

      </div>
    </footer>
  );
}
