"use client";

import { useActionState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import AuthSplitLayout from "@/components/auth/AuthSplitLayout";

type FormState = { error?: string } | undefined;

const inputClass =
  "w-full rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] py-2.5 pl-10 pr-3 text-sm text-[var(--color-text-primary)] transition-colors placeholder:text-[var(--color-text-ghost)] focus:border-ember-500/60 focus:outline-none focus:ring-2 focus:ring-ember-500/50";

export default function RegisterPage() {
  const { register } = useAuth();

  async function handleRegister(_prev: FormState, formData: FormData): Promise<FormState> {
    const email     = formData.get("email") as string;
    const password  = formData.get("password") as string;
    const full_name = (formData.get("full_name") as string) || undefined;
    const org_name  = formData.get("org_name") as string;

    if (password.length < 8) return { error: "Password must be at least 8 characters." };

    try {
      await register({ email, password, full_name, org_name });
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Registration failed." };
    }
  }

  const [state, action, pending] = useActionState(handleRegister, undefined);

  return (
    <AuthSplitLayout
      eyebrow="Hospital sign up"
      title="Create your workspace."
      subtitle="Set up your hospital operations copilot in minutes."
    >
      <form action={action} className="space-y-4 rounded-2xl border border-[var(--color-border-default)] bg-[var(--color-surface)] p-6 shadow-[0_2px_4px_rgba(20,15,5,0.06),0_24px_60px_-20px_rgba(20,15,5,0.35)]">
        {state?.error && (
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-400">
            {state.error}
          </div>
        )}

        <div>
          <label className="mb-1.5 block text-sm text-[var(--color-text-soft)]" htmlFor="org_name">Hospital / facility name</label>
          <div className="relative">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 21h18M5 21V7l7-4 7 4v14M9 9h1m4 0h1m-6 4h1m4 0h1m-6 4h1m4 0h1" />
            </svg>
            <input id="org_name" name="org_name" type="text" required className={inputClass} placeholder="Metro General Hospital" />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm text-[var(--color-text-soft)]" htmlFor="full_name">
            Your name <span className="text-[var(--color-text-ghost)]">(optional)</span>
          </label>
          <div className="relative">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <input id="full_name" name="full_name" type="text" className={inputClass} placeholder="Dr. Priya Sharma" />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm text-[var(--color-text-soft)]" htmlFor="email">Work email</label>
          <div className="relative">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9" />
            </svg>
            <input id="email" name="email" type="email" required autoComplete="email" className={inputClass} placeholder="ops@metrohospital.org" />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm text-[var(--color-text-soft)]" htmlFor="password">Password</label>
          <div className="relative">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 10-8 0v4h8z" />
            </svg>
            <input id="password" name="password" type="password" required autoComplete="new-password" minLength={8} className={inputClass} placeholder="Min. 8 characters" />
          </div>
        </div>

        <button
          type="submit"
          disabled={pending}
          className="btn-primary w-full rounded-xl py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Creating workspace…" : "Create workspace"}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-[var(--color-text-faint)]">
        Already have an account?{" "}
        <Link href="/login" className="text-[var(--color-accent)] transition-colors hover:text-ember-200">
          Sign in
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
