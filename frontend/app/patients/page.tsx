"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, createPatient, listPatients, summarizePatient } from "@/lib/api";
import type { Patient } from "@/lib/types";
import { TopBar } from "@/components/TopBar";

export default function PatientsPage() {
  const router = useRouter();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // new-patient form
  const [ref, setRef] = useState("");
  const [name, setName] = useState("");
  const [bundle, setBundle] = useState("");
  const [creating, setCreating] = useState(false);

  // summary
  const [summaryFor, setSummaryFor] = useState<string | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);

  async function load() {
    setLoading(true);
    try {
      setPatients(await listPatients());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!ref) return;
    setCreating(true);
    setError(null);
    try {
      const p = await createPatient({
        patient_ref: ref,
        display_name: name || null,
        fhir_bundle_path: bundle || null,
      });
      setRef("");
      setName("");
      setBundle("");
      setPatients((prev) => [...prev.filter((x) => x.id !== p.id), p]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  function startEncounter(p: Patient) {
    // Carry the selected patient forward to a fresh encounter workspace.
    const ref = `enc-${Date.now()}`;
    router.push(`/encounters/new?patient_id=${p.id}&patient_name=${encodeURIComponent(p.display_name ?? p.patient_ref)}&encounter_ref=${ref}`);
  }

  async function runSummary(p: Patient) {
    setSummaryFor(p.id);
    setSummary(null);
    setError(null);
    try {
      setSummary(await summarizePatient(p.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  return (
    <div className="min-h-[calc(100vh-2rem)]">
      <TopBar title="Patients" subtitle="Select a patient to start a consultation" />

      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Patients
            </h2>
            {loading ? (
              <p className="text-sm text-slate-400">Loading…</p>
            ) : patients.length === 0 ? (
              <p className="text-sm text-slate-400">No patients yet — create one to begin.</p>
            ) : (
              <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
                {patients.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-4 px-4 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">
                        {p.display_name ?? "Unnamed"}
                      </p>
                      <p className="truncate text-xs text-slate-500">
                        FHIR Patient/{p.patient_ref}
                        {p.fhir_bundle_path ? " · context available" : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      {p.fhir_bundle_path && (
                        <button
                          onClick={() => runSummary(p)}
                          disabled={summaryFor === p.id}
                          className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
                        >
                          Summarize
                        </button>
                      )}
                      <button
                        onClick={() => startEncounter(p)}
                        className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700"
                      >
                        Start encounter
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {summary && (
              <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-slate-900">Patient summary</h3>
                <p className="mt-1 text-sm text-slate-700">
                  {String(summary.one_liner ?? "")}
                </p>
                {Array.isArray(summary.sections) && (
                  <div className="mt-3 space-y-3">
                    {(summary.sections as Array<Record<string, unknown>>).map((s, i) => (
                      <div key={i}>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          {String(s.heading ?? "")}
                        </p>
                        {Array.isArray(s.bullets) && (s.bullets as unknown[]).length > 0 ? (
                          <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
                            {(s.bullets as Array<Record<string, unknown>>).map((b, j) => (
                              <li key={j}>{String(b.text ?? "")}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-0.5 text-xs italic text-slate-400">No data</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Add patient
            </h2>
            <form
              onSubmit={create}
              className="space-y-3 rounded-xl border border-slate-200 bg-white p-5"
            >
              <label className="block space-y-1">
                <span className="text-xs font-medium text-slate-600">FHIR Patient id *</span>
                <input
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  placeholder="patient-1"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-medium text-slate-600">Display name</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Jane Doe"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-medium text-slate-600">
                  FHIR bundle path (for context + summary)
                </span>
                <input
                  value={bundle}
                  onChange={(e) => setBundle(e.target.value)}
                  placeholder="/path/to/r4_patient_bundle.json"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </label>
              <button
                type="submit"
                disabled={creating || !ref}
                className="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
              >
                {creating ? "Adding…" : "Add patient"}
              </button>
            </form>
          </section>
        </div>
      </main>
    </div>
  );
}
