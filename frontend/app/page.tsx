"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken, me } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    me()
      .then(() => router.replace("/patients"))
      .catch(() => router.replace("/login"));
  }, [router]);

  return (
    <div className="flex h-[calc(100vh-2rem)] items-center justify-center">
      <p className="text-slate-400">Loading…</p>
    </div>
  );
}
