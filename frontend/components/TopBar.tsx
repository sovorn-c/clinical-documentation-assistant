"use client";

import { useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <svg width="20" height="16" viewBox="0 0 20 16" fill="none" aria-hidden="true">
        <rect x="0" y="6" width="3" height="4" rx="1.5" className="fill-teal-300" />
        <rect x="5" y="2" width="3" height="12" rx="1.5" className="fill-teal-500" />
        <rect x="10" y="5" width="3" height="6" rx="1.5" className="fill-teal-400" />
        <rect x="15" y="0" width="3" height="16" rx="1.5" className="fill-teal-600" />
      </svg>
      <span className="font-serif text-base font-semibold tracking-tight text-ink-900">CDA</span>
    </span>
  );
}

export function TopBar({ title, subtitle }: { title: string; subtitle?: string }) {
  const router = useRouter();

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <header className="border-b border-ink-200 bg-ink-25/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
        <div className="flex items-center gap-3.5">
          <button
            onClick={() => router.push("/patients")}
            className="rounded-md transition hover:opacity-70"
            aria-label="Go to patients"
          >
            <Wordmark />
          </button>
          <span className="h-5 w-px bg-ink-200" aria-hidden="true" />
          <div>
            <h1 className="text-sm font-semibold text-ink-900">{title}</h1>
            {subtitle && <p className="text-xs text-ink-500">{subtitle}</p>}
          </div>
        </div>
        <button
          onClick={logout}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-ink-600 transition hover:bg-ink-100"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
