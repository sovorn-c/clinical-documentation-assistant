"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, createEncounter, uploadAudio } from "@/lib/api";
import { TopBar } from "@/components/TopBar";

function NewEncounterInner() {
  const router = useRouter();
  const params = useSearchParams();
  const patientId = params.get("patient_id") ?? "";
  const patientName = params.get("patient_name") ?? "";
  const encounterRef = params.get("encounter_ref") ?? `enc-${Date.now()}`;

  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(e: React.FormEvent) {
    e.preventDefault();
    if (!patientId) {
      setError("No patient selected.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const enc = await createEncounter({
        patient_id: patientId,
        encounter_ref: encounterRef,
        audio_path: null,
      });
      if (file) {
        await uploadAudio(enc.id, file);
      }
      router.replace(`/encounters/${enc.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-[calc(100vh-2rem)]">
      <TopBar title="New encounter" subtitle={patientName || patientId} />
      <main className="mx-auto max-w-xl px-6 py-10">
        <form onSubmit={start} className="space-y-6 rounded-2xl border border-slate-200 bg-white p-8">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Upload consultation audio</h2>
            <p className="mt-1 text-sm text-slate-500">
              Choose the recorded consultation audio file. The backend transcribes it and drafts a
              SOAP note for your review.
            </p>
          </div>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Audio file</span>
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-brand-50 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-brand-700 hover:file:bg-brand-100"
            />
            {file && (
              <p className="text-xs text-slate-500">
                {file.name} — {(file.size / 1024).toFixed(0)} KB
              </p>
            )}
          </label>

          <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
            Encounter ref: <code className="font-mono">{encounterRef}</code>
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {busy ? "Creating…" : "Create encounter & transcribe"}
          </button>
        </form>
      </main>
    </div>
  );
}

export default function NewEncounterPage() {
  return (
    <Suspense fallback={<div className="p-10 text-sm text-slate-400">Loading…</div>}>
      <NewEncounterInner />
    </Suspense>
  );
}
