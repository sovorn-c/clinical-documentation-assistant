"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, login, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("clinician");
  const [password, setPassword] = useState("changeme");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const tok = await login(username, password);
      setToken(tok.access_token);
      router.replace("/patients");
    } catch (err) {
      setError(err instanceof ApiError ? "Incorrect username or password" : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-[calc(100vh-2rem)] items-center justify-center overflow-hidden px-4">
      {/* Ambient waveform texture — quiet, decorative, echoes the audio-capture subject */}
      <div
        className="pointer-events-none absolute inset-0 flex items-end justify-center gap-1.5 opacity-[0.06]"
        aria-hidden="true"
      >
        {Array.from({ length: 40 }).map((_, i) => (
          <div
            key={i}
            className="w-2 rounded-full bg-teal-600"
            style={{ height: `${18 + ((i * 37) % 60)}%` }}
          />
        ))}
      </div>

      <form
        onSubmit={submit}
        className="relative w-full max-w-sm space-y-6 rounded-2xl border border-ink-200 bg-white p-8 shadow-[0_1px_2px_rgba(24,36,32,0.04),0_8px_24px_rgba(24,36,32,0.06)]"
      >
        <div>
          <div className="mb-4 flex items-center gap-2">
            <svg width="22" height="18" viewBox="0 0 20 16" fill="none" aria-hidden="true">
              <rect x="0" y="6" width="3" height="4" rx="1.5" className="fill-teal-300" />
              <rect x="5" y="2" width="3" height="12" rx="1.5" className="fill-teal-500" />
              <rect x="10" y="5" width="3" height="6" rx="1.5" className="fill-teal-400" />
              <rect x="15" y="0" width="3" height="16" rx="1.5" className="fill-teal-600" />
            </svg>
            <span className="font-serif text-lg font-semibold tracking-tight text-ink-900">CDA</span>
          </div>
          <h1 className="text-xl font-semibold text-ink-900">Clinical Documentation Assistant</h1>
          <p className="mt-1 text-sm text-ink-500">Sign in to continue.</p>
        </div>

        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-ink-700">Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-lg border border-ink-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
            autoComplete="username"
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-ink-700">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-ink-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
            autoComplete="current-password"
          />
        </label>

        {error && (
          <p className="rounded-lg bg-brick-50 px-3 py-2 text-sm text-brick-700" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:opacity-60"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-center text-xs text-ink-400">
          Demo clinician seeded as <code className="font-mono">clinician / changeme</code>.
        </p>
      </form>
    </div>
  );
}
