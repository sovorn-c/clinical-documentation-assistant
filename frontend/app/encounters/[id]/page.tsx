"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  approveCodes,
  approveNote,
  approveReferral,
  exportFhir,
  generateNote,
  generateReferral,
  getEncounter,
  getNoteVersions,
  getReferral,
  getTranscript,
  listAudit,
  listCodes,
  listExports,
  me,
  suggestCodes,
  editNote,
} from "@/lib/api";
import type {
  AuditEntry,
  CodeSuggestion,
  Encounter,
  FhirExport,
  Note,
  Referral,
  SOAPNote,
  Transcript,
} from "@/lib/types";
import { TopBar } from "@/components/TopBar";
import { SoapEditor } from "@/components/SoapEditor";

export default function EncounterWorkspace() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const [encounter, setEncounter] = useState<Encounter | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [codes, setCodes] = useState<CodeSuggestion[]>([]);
  const [referral, setReferral] = useState<Referral | null>(null);
  const [exports, setExports] = useState<FhirExport[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);

  const [approver, setApprover] = useState("Dr. Demo");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [enc, t, ns, cs, ref, ex, au] = await Promise.allSettled([
        getEncounter(id),
        getTranscript(id),
        getNoteVersions(id),
        listCodes(id),
        getReferral(id),
        listExports(id),
        listAudit(id),
      ]);
      if (enc.status === "fulfilled") setEncounter(enc.value);
      setTranscript(t.status === "fulfilled" ? t.value : null);
      setNotes(ns.status === "fulfilled" ? ns.value : []);
      setCodes(cs.status === "fulfilled" ? cs.value : []);
      setReferral(ref.status === "fulfilled" ? ref.value : null);
      setExports(ex.status === "fulfilled" ? ex.value : []);
      setAudit(au.status === "fulfilled" ? au.value : []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }, [id]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const user = await me().catch(() => null);
        if (user?.display_name) setApprover(user.display_name);
        await reload();
      } finally {
        setLoading(false);
      }
    })();
  }, [reload]);

  const latestNote = notes[notes.length - 1] ?? null;
  const aiNote = notes.find((n) => n.source === "ai") ?? null;
  const noteApproved = audit.some((a) => a.action === "approve_note");
  const codesApproved = audit.some((a) => a.action === "approve_codes");
  const referralApproved = referral?.approved ?? audit.some((a) => a.action === "approve_referral");
  const exported = exports.length > 0;

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-2rem)]">
        <TopBar title="Encounter" />
        <p className="p-10 text-sm text-slate-400">Loading…</p>
      </div>
    );
  }

  if (!encounter) {
    return (
      <div className="min-h-[calc(100vh-2rem)]">
        <TopBar title="Encounter" />
        <p className="p-10 text-sm text-red-600">Encounter not found.</p>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-2rem)]">
      <TopBar
        title={`Encounter ${encounter.encounter_ref}`}
        subtitle={`Status: ${encounter.status.replace(/_/g, " ")}`}
      />

      <main className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <Stepper encounter={encounter} hasNote={!!latestNote} hasCodes={codes.length > 0} hasReferral={!!referral} exported={exported} />

        {/* 1. Audio + transcribe */}
        <Card
          title="1 · Transcribe & draft note"
          status={latestNote ? "done" : "pending"}
          statusLabel={latestNote ? "Drafted" : "Awaiting transcription"}
        >
          <p className="text-sm text-slate-600">
            {encounter.audio_path ? (
              <>
                Audio uploaded: <code className="font-mono text-xs">{encounter.audio_path}</code>
              </>
            ) : (
              "No audio attached to this encounter."
            )}
          </p>
          <button
            onClick={() => run("generate", () => generateNote(id))}
            disabled={busy !== null}
            className="mt-3 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {busy === "generate" ? "Transcribing…" : latestNote ? "Regenerate draft" : "Generate draft note"}
          </button>
        </Card>

        {/* 2. Transcript */}
        {transcript && (
          <Card title="Transcript" status="done" statusLabel="Review">
            <div className="space-y-1.5">
              {transcript.utterances.map((u) => (
                <div key={u.id} className="flex gap-3 text-sm">
                  <span
                    className={
                      "w-20 shrink-0 text-xs font-semibold uppercase " +
                      (u.role === "CLINICIAN" ? "text-brand-700" : "text-slate-500")
                    }
                  >
                    {u.role}
                  </span>
                  <span className="text-slate-700">{u.text}</span>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* 3. Edit SOAP */}
        {latestNote && (
          <Card
            title="2 · Review & edit SOAP note"
            status={noteApproved ? "approved" : "pending"}
            statusLabel={noteApproved ? "Approved" : "Needs approval"}
          >
            <SoapEditor
              note={latestNote}
              aiNote={aiNote && aiNote.id !== latestNote.id ? aiNote : null}
              saving={busy === "saveNote"}
              onSave={(note: SOAPNote) => run("saveNote", () => editNote(id, note))}
            />
            <div className="mt-4 border-t border-slate-100 pt-4">
              <button
                onClick={() => run("approveNote", () => approveNote(id, approver))}
                disabled={busy !== null || noteApproved}
                className="rounded-lg border border-brand-600 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50 disabled:opacity-50"
              >
                {noteApproved ? "Note approved ✓" : "Approve note"}
              </button>
            </div>
          </Card>
        )}

        {/* 4. Codes */}
        {latestNote && (
          <Card
            title="3 · Suggested codes"
            status={codes.length === 0 ? "pending" : codesApproved ? "approved" : "review"}
            statusLabel={
              codes.length === 0
                ? "Not generated"
                : codesApproved
                  ? "Approved"
                  : "Awaiting approval"
            }
          >
            <button
              onClick={() => run("codes", () => suggestCodes(id))}
              disabled={busy !== null}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
            >
              {busy === "codes" ? "Suggesting…" : codes.length ? "Re-suggest codes" : "Suggest codes"}
            </button>
            {codes.length > 0 && (
              <ul className="mt-3 divide-y divide-slate-100 rounded-xl border border-slate-200">
                {codes.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
                    <div>
                      <p className="text-sm font-medium text-slate-900">
                        <code className="font-mono">{c.code}</code> — {c.description}
                      </p>
                      <p className="text-xs text-slate-500">
                        rank {c.rank} · {Math.round(c.confidence * 100)}% confidence
                      </p>
                    </div>
                    <span
                      className={
                        "rounded-full px-2 py-0.5 text-xs font-medium " +
                        (c.approved ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500")
                      }
                    >
                      {c.approved ? "approved" : "pending"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {codes.length > 0 && (
              <button
                onClick={() => run("approveCodes", () => approveCodes(id, approver))}
                disabled={busy !== null || codesApproved}
                className="mt-3 rounded-lg border border-brand-600 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50 disabled:opacity-50"
              >
                {codesApproved ? "Codes approved ✓" : "Approve all codes"}
              </button>
            )}
          </Card>
        )}

        {/* 5. Referral */}
        {latestNote && (
          <Card
            title="4 · Referral letter"
            status={!referral ? "pending" : referralApproved ? "approved" : "review"}
            statusLabel={!referral ? "Not generated" : referralApproved ? "Approved" : "Awaiting approval"}
          >
            <button
              onClick={() => run("referral", () => generateReferral(id))}
              disabled={busy !== null}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
            >
              {busy === "referral" ? "Generating…" : referral ? "Regenerate referral" : "Generate referral"}
            </button>
            {referral && (
              <>
                <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                  {referral.letter_text}
                </pre>
                <button
                  onClick={() => run("approveReferral", () => approveReferral(id, approver))}
                  disabled={busy !== null || referralApproved}
                  className="mt-3 rounded-lg border border-brand-600 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50 disabled:opacity-50"
                >
                  {referralApproved ? "Referral approved ✓" : "Approve referral"}
                </button>
              </>
            )}
          </Card>
        )}

        {/* 6. Export */}
        {latestNote && (
          <Card
            title="5 · Approve & export to FHIR"
            status={exported ? "done" : "pending"}
            statusLabel={exported ? "Exported" : "Awaiting approval + export"}
          >
            <p className="text-sm text-slate-600">
              Export is gated: the note{codes.length > 0 ? ", codes" : ""}
              {referral ? ", and referral" : ""} must each be approved first.
            </p>
            <button
              onClick={() => run("export", () => exportFhir(id))}
              disabled={busy !== null}
              className="mt-3 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
            >
              {busy === "export" ? "Exporting…" : "Export to FHIR"}
            </button>
            {exports.length > 0 && (
              <ul className="mt-3 space-y-2">
                {exports.map((e) => (
                  <li key={e.id} className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-sm font-medium text-slate-900">
                      {e.resource_type}{" "}
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                        FHIR {e.fhir_version}
                      </span>
                    </p>
                    <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-slate-50 p-2 text-xs text-slate-600">
                      {e.json_text}
                    </pre>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}

        {/* 7. Audit trail */}
        <Card title="Audit trail" status="done" statusLabel={`${audit.length} events`}>
          {audit.length === 0 ? (
            <p className="text-sm text-slate-400">No events yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {audit.map((a) => (
                <li key={a.id} className="flex items-start gap-3 py-2 text-sm">
                  <span
                    className={
                      "mt-1 h-2 w-2 shrink-0 rounded-full " +
                      (a.actor === "user" ? "bg-brand-500" : "bg-slate-300")
                    }
                  />
                  <div className="min-w-0">
                    <p className="text-slate-800">
                      <span className="font-medium">{a.action.replace(/_/g, " ")}</span>
                      {a.actor_name ? ` · ${a.actor_name}` : ""}
                    </p>
                    <p className="text-xs text-slate-400">
                      {new Date(a.created_at).toLocaleString()}
                      {a.artifact_type ? ` · ${a.artifact_type}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </main>
    </div>
  );
}

function Stepper({
  encounter,
  hasNote,
  hasCodes,
  hasReferral,
  exported,
}: {
  encounter: Encounter;
  hasNote: boolean;
  hasCodes: boolean;
  hasReferral: boolean;
  exported: boolean;
}) {
  const steps = [
    { label: "Audio", done: !!encounter.audio_path },
    { label: "Transcribe", done: hasNote },
    { label: "Edit note", done: hasNote },
    { label: "Codes", done: hasCodes },
    { label: "Referral", done: hasReferral },
    { label: "Export", done: exported },
  ];
  return (
    <ol className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3">
      {steps.map((s, i) => (
        <li key={s.label} className="flex items-center gap-2">
          <span
            className={
              "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold " +
              (s.done ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-400")
            }
          >
            {s.done ? "✓" : i + 1}
          </span>
          <span className={"text-sm " + (s.done ? "text-slate-800" : "text-slate-400")}>
            {s.label}
          </span>
          {i < steps.length - 1 && <span className="text-slate-300">→</span>}
        </li>
      ))}
    </ol>
  );
}

function Card({
  title,
  status,
  statusLabel,
  children,
}: {
  title: string;
  status: "pending" | "review" | "approved" | "done";
  statusLabel: string;
  children: React.ReactNode;
}) {
  const pill = {
    pending: "bg-slate-100 text-slate-500",
    review: "bg-amber-100 text-amber-700",
    approved: "bg-brand-100 text-brand-700",
    done: "bg-emerald-100 text-emerald-700",
  }[status];
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        <span className={"rounded-full px-2.5 py-1 text-xs font-medium " + pill}>{statusLabel}</span>
      </div>
      {children}
    </section>
  );
}
