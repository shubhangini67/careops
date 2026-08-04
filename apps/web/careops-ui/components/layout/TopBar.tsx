"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useDashboardCtx } from "@/context/DashboardContext";
import { useTheme } from "@/context/ThemeContext";
import { getActionQueue } from "@/lib/api";

function ThemeToggle() {
  const ctx = useTheme();
  if (!ctx) return null;
  const { theme, toggleTheme } = ctx;

  return (
    <button
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="flex shrink-0 items-center justify-center rounded-lg p-2 text-[var(--color-text-faint)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-accent)]"
    >
      {theme === "dark" ? (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.36 6.36l-.71-.71M6.34 6.34l-.71-.71m12.73.01l-.71.71M6.34 17.66l-.71.71M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ) : (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      )}
    </button>
  );
}

export default function TopBar() {
  const { user, loading, logout } = useAuth();
  const pathname         = usePathname();
  const router           = useRouter();
  const dashCtx          = useDashboardCtx();
  const [userMenuOpen, setUserMenuOpen]     = useState(false);
  const [quickOpen, setQuickOpen]           = useState(false);
  const [pendingCount, setPendingCount]     = useState(0);
  const userMenuRef    = useRef<HTMLDivElement>(null);
  const quickRef       = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const t = e.target as Node;
      if (userMenuRef.current && !userMenuRef.current.contains(t)) setUserMenuOpen(false);
      if (quickRef.current && !quickRef.current.contains(t)) setQuickOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!user) return;
    getActionQueue("pending").then((rows) => setPendingCount(rows.length)).catch(() => {});
  }, [user]);

  function handleHistory() {
    router.push("/data");
  }

  // /concierge is a separate, no-auth consumer experience -- operator chrome
  // must never show there, even if this browser also has an operator session
  // logged in (e.g. a restaurant owner previewing the guest flow).
  if (pathname.startsWith("/concierge")) return null;

  // Same reasoning as Sidebar.tsx: AuthContext starts every fresh page load
  // with user=null even when a valid session exists, only resolving after an
  // async /auth/me call -- a same-shaped skeleton avoids a full topbar
  // disappearance on every reload instead of just a genuine logged-out state.
  if (loading) {
    return (
      <header className="sticky top-0 z-40 border-b border-[var(--color-border-default)] bg-[var(--color-surface-raised)]/95">
        <div className="flex h-14 items-center gap-2 px-4 sm:px-6">
          <div className="h-8 w-40 animate-pulse rounded-lg bg-[var(--color-surface-sunken)]" />
          <div className="flex-1" />
          <div className="h-8 w-8 animate-pulse rounded-lg bg-[var(--color-surface-sunken)]" />
          <div className="h-8 w-8 animate-pulse rounded-lg bg-[var(--color-surface-sunken)]" />
          <div className="h-8 w-24 animate-pulse rounded-lg bg-[var(--color-surface-sunken)]" />
        </div>
      </header>
    );
  }

  if (!user) return null;

  const onPlanning = pathname === "/planning";
  const today = new Date();

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border-default)] bg-[var(--color-surface-raised)]/95 shadow-[0_1px_0_rgba(0,0,0,0.02),0_8px_24px_-16px_rgba(60,40,15,0.35)] backdrop-blur-md dark:shadow-[0_1px_0_rgba(255,255,255,0.03),0_8px_24px_-14px_rgba(0,0,0,0.6)]">
      <div className="flex h-14 items-center gap-2 px-4 sm:px-6">
        <div className="hidden shrink-0 items-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-soft)] md:flex">
          <svg className="h-3.5 w-3.5 shrink-0 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
          {today.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
        </div>

        <div className="flex-1" />

        {onPlanning && dashCtx && dashCtx.dashStatus !== "idle" && (
          <button
            onClick={dashCtx.doReset}
            className="hidden items-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-soft)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text-primary)] sm:flex"
          >
            <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            New Run
          </button>
        )}

        <button
          onClick={handleHistory}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-faint)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text-primary)]"
        >
          <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="hidden sm:block">History</span>
        </button>

        {/* Notification bell -- pending Action Queue count, real data */}
        <Link
          href="/action-center"
          className="relative flex shrink-0 items-center justify-center rounded-lg p-2 text-[var(--color-text-faint)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-accent)]"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          {pendingCount > 0 && (
            <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full px-0.5 text-[9px] font-bold text-white" style={{ background: "var(--color-critical)" }}>
              {pendingCount}
            </span>
          )}
        </Link>

        <ThemeToggle />

        {/* Quick Actions */}
        <div className="relative shrink-0" ref={quickRef}>
          <button
            onClick={() => setQuickOpen((v) => !v)}
            className="btn-primary flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            <span className="hidden sm:inline">Quick Actions</span>
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
          </button>
          {quickOpen && (
            <div className="absolute right-0 top-full mt-1.5 w-56 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-1.5 shadow-xl z-50">
              <Link href="/planning" onClick={() => setQuickOpen(false)} className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--color-text-soft)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-sunken)] transition-colors">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                Run Scenario Plan
              </Link>
              <Link href="/action-center" onClick={() => setQuickOpen(false)} className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--color-text-soft)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-sunken)] transition-colors">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>
                Go to Approval Queue
              </Link>
              <Link href="/chat" onClick={() => setQuickOpen(false)} className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--color-text-soft)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-sunken)] transition-colors">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
                Policy Assistant
              </Link>
            </div>
          )}
        </div>

        <div className="relative shrink-0" ref={userMenuRef}>
          <button
            onClick={() => setUserMenuOpen(v => !v)}
            className="flex items-center gap-2 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs text-[var(--color-text-soft)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text-primary)]"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-ember-500/20 ring-1 ring-ember-400/30 text-[10px] font-bold text-ember-500 dark:text-ember-300">
              {(user.full_name ?? user.email).slice(0, 2).toUpperCase()}
            </div>
            <div className="hidden text-left leading-tight sm:block">
              <p className="max-w-[110px] truncate font-semibold text-[var(--color-text-primary)]">{user.full_name ?? user.email.split("@")[0]}</p>
              <p className="text-[10px] capitalize text-[var(--color-text-faint)]">{user.role}</p>
            </div>
            <svg className="h-3 w-3 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-1.5 w-48 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-1.5 shadow-xl z-50">
              <div className="px-3 py-2 border-b border-[var(--color-border-soft)] mb-1">
                <p className="text-xs font-medium text-[var(--color-text-primary)] truncate">{user.full_name ?? user.email}</p>
                <p className="text-[10px] text-[var(--color-text-faint)] mt-0.5">{user.org_name} · {user.role}</p>
              </div>
              {user.role === "owner" && (
                <>
                  <Link href="/settings" onClick={() => setUserMenuOpen(false)} className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--color-text-soft)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-sunken)] transition-colors">
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    Settings
                  </Link>
                  <div className="border-t border-[var(--color-border-soft)] my-1" />
                </>
              )}
              <button onClick={() => { setUserMenuOpen(false); logout(); }} className="flex w-full items-center gap-2 px-3 py-2 text-xs text-rose-500 dark:text-rose-400/80 hover:text-rose-600 dark:hover:text-rose-300 hover:bg-[var(--color-surface-sunken)] transition-colors">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
