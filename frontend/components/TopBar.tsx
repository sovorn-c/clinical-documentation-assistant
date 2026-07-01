"use client";

import { useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

export function TopBar({ title, subtitle }: { title: string; subtitle?: string }) {
  const router = useRouter();

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/patients")}
            className="text-sm font-semibold text-brand-700 hover:text-brand-600"
          >
            CDA
          </button>
          <span className="text-slate-300">/</span>
          <div>
            <h1 className="text-sm font-semibold text-slate-900">{title}</h1>
            {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
          </div>
        </div>
        <button
          onClick={logout}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
