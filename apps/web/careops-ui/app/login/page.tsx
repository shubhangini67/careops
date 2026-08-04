"use client";

import { useActionState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import AuthSplitLayout from "@/components/auth/AuthSplitLayout";

type FormState = { error?: string } | undefined;

export default function LoginPage() {
  const { login } = useAuth();

  async function handleLogin(_prev: FormState, formData: FormData): Promise<FormState> {
    const email    = formData.get("email") as string;
    const password = formData.get("password") as string;
    try {
      await login({ email, password });
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Login failed." };
    }
  }

  const [state, action, pending] = useActionState(handleLogin, undefined);

  return (
    <AuthSplitLayout
      eyebrow="Hospital sign in"
      title="Welcome back."
      subtitle="Sign in to your hospital operations workspace."
    >
      <form action={action} className="space-y-4 rounded-2xl border border-[var(--color-border-default)] bg-[var(--color-surface)] p-6 shadow-[0_2px_4px_rgba(20,15,5,0.06),0_24px_60px_-20px_rgba(20,15,5,0.35)]">
        {state?.error && (
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-400">
            {state.error}
          </div>
        )}

        <div>
          <label className="mb-1.5 block text-sm text-[var(--color-text-soft)]" htmlFor="email">Email</label>
          <div className="relative">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9" />
            </svg>
            <input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              className="w-full rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] py-2.5 pl-10 pr-3 text-sm text-[var(--color-text-primary)] transition-colors placeholder:text-[var(--color-text-ghost)] focus:border-ember-500/60 focus:outline-none focus:ring-2 focus:ring-ember-500/50"
              placeholder="you@hospital.org"
            />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm text-[var(--color-text-soft)]" htmlFor="password">Password</label>
          <div className="relative">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 10-8 0v4h8z" />
            </svg>
            <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
              className="w-full rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] py-2.5 pl-10 pr-3 text-sm text-[var(--color-text-primary)] transition-colors placeholder:text-[var(--color-text-ghost)] focus:border-ember-500/60 focus:outline-none focus:ring-2 focus:ring-ember-500/50"
              placeholder="••••••••"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={pending}
          className="btn-primary w-full rounded-xl py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-[var(--color-text-faint)]">
        No account?{" "}
        <Link href="/register" className="text-[var(--color-accent)] transition-colors hover:text-ember-200">
          Create workspace
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
