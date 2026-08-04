"use client";

import Image from "next/image";
import Link from "next/link";
import { useRef, useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

const NAV_LINKS = [
  { href: "/dashboard",      label: "Operations Dashboard", hue: "#0ea5e9", icon: <svg className="h-[17px] w-[17px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg> },
  { href: "/analytics",      label: "Capacity Forecast",    hue: "#818cf8", icon: <svg className="h-[17px] w-[17px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M3 17l6-6 4 4 8-8m0 0h-5m5 0v5" /></svg> },
  { href: "/planning",       label: "Scenario Planner",     hue: "#34d399", icon: <svg className="h-[17px] w-[17px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg> },
  { href: "/chat",           label: "Policy Assistant",     hue: "#a855f7", icon: <svg className="h-[17px] w-[17px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg> },
  { href: "/data",           label: "Resources & Supplies", hue: "#f59e0b", icon: <svg className="h-[17px] w-[17px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg> },
  { href: "/action-center",  label: "Approval Queue",       hue: "#fb7185", icon: <svg className="h-[17px] w-[17px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg> },
];

const ADMIN_LINKS = [
  { href: "/settings", label: "Settings", ownerOnly: true },
];

const AdminIcon = <svg className="h-[18px] w-[18px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>;

export default function Sidebar() {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const [adminOpenState, setAdminOpen] = useState(false);
  const adminRef = useRef<HTMLDivElement>(null);
  const adminActive = ADMIN_LINKS.some((l) => pathname === l.href);
  // Open whenever an Admin sub-link is the active route, regardless of the
  // manual toggle state -- derived, not synced via an effect + setState.
  const adminOpen = adminOpenState || adminActive;

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (adminRef.current && !adminRef.current.contains(e.target as Node) && !adminActive) setAdminOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [adminActive]);

  // Legacy consumer/restaurant routes hidden from operator chrome
  if (pathname.startsWith("/concierge") || pathname.startsWith("/market") || pathname.startsWith("/connectors")) return null;

  // AuthContext always starts a fresh page load with user=null, even when a
  // valid session cookie exists -- it only populates `user` after an async
  // /auth/me round-trip. Returning null for that whole window (previously
  // the only branch here) made the sidebar visibly vanish on every reload,
  // not just on a genuine logged-out state. A same-shaped skeleton avoids
  // the layout-shift/disappearance; only a real logged-out state (loading
  // finished, still no user) renders nothing.
  if (loading) {
    return (
      <aside className="sticky top-0 z-30 flex h-screen w-[228px] shrink-0 flex-col border-r border-[var(--color-border-default)] bg-[var(--color-surface-raised)]">
        <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-[var(--color-border-default)] px-4">
          <div className="h-9 w-9 shrink-0 animate-pulse rounded-lg bg-[var(--color-surface-sunken)]" />
          <div className="h-3.5 w-24 animate-pulse rounded bg-[var(--color-surface-sunken)]" />
        </div>
        <div className="flex flex-1 flex-col gap-1.5 px-3.5 py-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-lg bg-[var(--color-surface-sunken)]" />
          ))}
        </div>
      </aside>
    );
  }

  if (!user) return null;

  return (
    <aside className="sticky top-0 z-30 flex h-screen w-[228px] shrink-0 flex-col border-r border-[var(--color-border-default)] bg-[var(--color-surface-raised)] shadow-[1px_0_0_rgba(0,0,0,0.02),8px_0_24px_-18px_rgba(60,40,15,0.4)] dark:shadow-[1px_0_0_rgba(255,255,255,0.03),8px_0_24px_-16px_rgba(0,0,0,0.6)]">
      {/* Brand -- fixed h-14 to match TopBar exactly, border-b runs the full
          sidebar width so it lines up with TopBar's own border-b across the
          corner instead of leaving a floating, unaligned gap there. */}
      <Link href="/dashboard" className="flex h-14 shrink-0 items-center gap-2.5 border-b border-[var(--color-border-default)] px-4">
        <div className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-lg bg-black ring-1 ring-[var(--color-border-default)]">
          <Image src="/ck-logo.png" alt="CareOps AI" width={30} height={30} className="h-[30px] w-[30px] object-contain" priority />
        </div>
        <div className="leading-tight">
          <div className="text-[14.5px] font-bold tracking-tight text-[var(--color-text-primary)]">CareOps AI</div>
          {user.org_name && <div className="text-[9px] uppercase tracking-[0.2em] text-[var(--color-accent)]">{user.org_name}</div>}
        </div>
      </Link>

      {/* Nav links */}
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3.5 py-4">
        {NAV_LINKS.map(({ href, label, icon, hue }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`relative flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px] transition-colors ${
                active
                  ? "bg-[var(--color-accent-soft)] font-bold text-[var(--color-accent)] shadow-[inset_0_0_0_1px_rgba(176,98,26,0.14)]"
                  : "font-medium text-[var(--color-text-soft)] hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-text-primary)]"
              }`}
            >
              {active && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full" style={{ background: "var(--color-accent)" }} />}
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md" style={{ background: `${hue}1f`, color: hue }}>
                {icon}
              </span>
              {label}
            </Link>
          );
        })}

        {/* Admin (collapsible) */}
        <div ref={adminRef} className="mt-1">
          <button
            onClick={() => setAdminOpen((v) => !v)}
            className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px] font-medium transition-colors ${
              adminActive ? "text-[var(--color-accent)]" : "text-[var(--color-text-soft)] hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md" style={{ background: "#94a3b81f", color: "#94a3b8" }}>
              {AdminIcon}
            </span>
            Admin
            <svg className={`ml-auto h-3.5 w-3.5 text-[var(--color-text-ghost)] transition-transform ${adminOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {adminOpen && (
            <div className="ml-6 mt-0.5 flex flex-col gap-0.5 border-l border-[var(--color-border-soft)] pl-3">
              {ADMIN_LINKS.filter((l) => !l.ownerOnly || user.role === "owner").map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className={`rounded-md px-2.5 py-1.5 text-[12.5px] font-medium transition-colors ${
                    pathname === l.href ? "text-[var(--color-accent)]" : "text-[var(--color-text-faint)] hover:text-[var(--color-text-primary)]"
                  }`}
                >
                  {l.label}
                </Link>
              ))}
            </div>
          )}
        </div>
      </nav>

      {/* Bottom promo card */}
      <div className="px-3.5 pb-4">
        <Link
          href="/chat"
          className="flex shrink-0 items-center gap-2.5 rounded-xl border border-[var(--color-accent)]/25 p-3 transition-transform hover:scale-[1.02]"
          style={{ background: "var(--color-accent-soft)" }}
        >
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg" style={{ background: "var(--color-accent)" }}>
            <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </div>
          <div className="min-w-0">
            <p className="text-[12px] font-bold text-[var(--color-text-primary)]">CareOps AI</p>
            <p className="mt-0.5 text-[10.5px] leading-tight text-[var(--color-text-faint)]">Intelligence for hospital operations</p>
          </div>
        </Link>
      </div>
    </aside>
  );
}
