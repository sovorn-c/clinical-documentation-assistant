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
        <form onSubmit={start} className="space-y-6 rounded-2xl border border-ink-200 bg-white p-8">
          <div>
            <div
              className="mb-4 flex h-12 items-end justify-center gap-1"
              aria-hidden="true"
            >
              {[40, 70, 100, 60, 85, 45].map((h, i) => (
                <div
                  key={i}
                  className="waveform-bar w-1.5 rounded-full bg-teal-300"
                  style={{ height: `${h}%`, animationDelay: `${i * 0.12}s` }}
                />
              ))}
            </div>
            <h2 className="text-center font-serif text-lg font-semibold text-ink-900">
              Upload consultation audio
            </h2>
            <p className="mt-1 text-center text-sm text-ink-500">
              Choose the recorded consultation audio file. The backend transcribes it and drafts a
              SOAP note for your review.
            </p>
          </div>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-ink-700">Audio file</span>
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-ink-600 file:mr-3 file:rounded-lg file:border-0 file:bg-teal-50 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-teal-700 hover:file:bg-teal-100"
            />
            {file && (
              <p className="text-xs text-ink-500">
                {file.name} — {(file.size / 1024).toFixed(0)} KB
              </p>
            )}
          </label>

          <div className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
            Encounter ref: <code className="font-mono">{encounterRef}</code>
          </div>

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
            {busy ? "Creating…" : "Create encounter & transcribe"}
          </button>
        </form>
      </main>
    </div>
  );
}

export default function NewEncounterPage() {
  return (
    <Suspense fallback={<div className="p-10 text-sm text-ink-400">Loading…</div>}>
      <NewEncounterInner />
    </Suspense>
  );
}
