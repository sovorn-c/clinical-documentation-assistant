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

function downloadJson(filename: string, jsonText: string) {
  const blob = new Blob([jsonText], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function fmtTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

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
        <p className="p-10 text-sm text-ink-400">Loading…</p>
      </div>
    );
  }

  if (!encounter) {
    return (
      <div className="min-h-[calc(100vh-2rem)]">
        <TopBar title="Encounter" />
        <p className="p-10 text-sm text-brick-600">Encounter not found.</p>
      </div>
    );
  }

  const railSteps = [
    { key: "step-transcribe", label: "Transcribe", done: !!latestNote },
    { key: "step-note", label: "Edit & approve note", done: noteApproved },
    { key: "step-codes", label: "Code", done: codesApproved },
    { key: "step-referral", label: "Refer", done: referralApproved },
    { key: "step-export", label: "Export", done: exported },
  ];

  return (
    <div className="min-h-[calc(100vh-2rem)]">
      <TopBar
        title={`Encounter ${encounter.encounter_ref}`}
        subtitle={`Status: ${encounter.status.replace(/_/g, " ")}`}
      />

      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <p className="mb-6 rounded-lg bg-brick-50 px-3 py-2 text-sm text-brick-700" role="alert">
            {error}
          </p>
        )}

        <MobileRail steps={railSteps} />

        <div className="lg:grid lg:grid-cols-[12rem_1fr] lg:gap-10">
          <ChartRail steps={railSteps} />

          <div className="mt-6 space-y-6 lg:mt-0">
            {/* 1. Audio + transcribe */}
            <Card
              id="step-transcribe"
              title="Transcribe & draft note"
              status={latestNote ? "done" : "pending"}
              statusLabel={latestNote ? "Drafted" : "Awaiting transcription"}
            >
              <p className="text-sm text-ink-600">
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
                className="mt-3 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:opacity-60"
              >
                {busy === "generate" ? "Transcribing…" : latestNote ? "Regenerate draft" : "Generate draft note"}
              </button>
            </Card>

            {/* 2. Transcript */}
            {transcript && (
              <Card id="transcript" title="Transcript" status="done" statusLabel="Review">
                <div className="space-y-2.5">
                  {transcript.utterances.map((u) => {
                    const isClinician = u.role === "CLINICIAN";
                    const isPatient = u.role === "PATIENT";
                    return (
                      <div
                        key={u.id}
                        className={
                          "flex gap-3 border-l-2 py-0.5 pl-3 " +
                          (isClinician ? "border-teal-400" : isPatient ? "border-ember-400" : "border-ink-200")
                        }
                      >
                        <span
                          className={
                            "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-semibold " +
                            (isClinician
                              ? "bg-teal-100 text-teal-700"
                              : isPatient
                                ? "bg-ember-100 text-ember-700"
                                : "bg-ink-100 text-ink-400")
                          }
                        >
                          {isClinician ? "C" : isPatient ? "P" : "?"}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-baseline gap-2">
                            <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                              {u.role}
                            </span>
                            {u.time_span && (
                              <span className="font-mono text-[10px] text-ink-400">
                                {fmtTimestamp(u.time_span.start)}
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-ink-800">{u.text}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* 3. Edit SOAP */}
            {latestNote && (
              <Card
                id="step-note"
                title="Review & edit SOAP note"
                status={noteApproved ? "approved" : "pending"}
                statusLabel={noteApproved ? "Approved" : "Needs approval"}
              >
                <SoapEditor
                  note={latestNote}
                  aiNote={aiNote && aiNote.id !== latestNote.id ? aiNote : null}
                  saving={busy === "saveNote"}
                  onSave={(note: SOAPNote) => run("saveNote", () => editNote(id, note))}
                />
                <div className="mt-4 border-t border-ink-100 pt-4">
                  <button
                    onClick={() => run("approveNote", () => approveNote(id, approver))}
                    disabled={busy !== null || noteApproved}
                    className="rounded-lg border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-700 transition hover:bg-teal-50 disabled:opacity-50"
                  >
                    {noteApproved ? "Note approved ✓" : "Approve note"}
                  </button>
                </div>
              </Card>
            )}

            {/* 4. Codes */}
            {latestNote && (
              <Card
                id="step-codes"
                title="Suggested codes"
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
                  className="rounded-lg bg-ink-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink-800 disabled:opacity-60"
                >
                  {busy === "codes" ? "Suggesting…" : codes.length ? "Re-suggest codes" : "Suggest codes"}
                </button>
                {codes.length > 0 && (
                  <ul className="mt-3 divide-y divide-ink-100 rounded-xl border border-ink-200">
                    {codes.map((c) => (
                      <li key={c.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
                        <div>
                          <p className="text-sm font-medium text-ink-900">
                            <code className="font-mono">{c.code}</code> — {c.description}
                          </p>
                          <p className="text-xs text-ink-500">
                            rank {c.rank} · {Math.round(c.confidence * 100)}% confidence
                          </p>
                        </div>
                        <span
                          className={
                            "rounded-full px-2 py-0.5 text-xs font-medium " +
                            (c.approved ? "bg-teal-100 text-teal-700" : "bg-ink-100 text-ink-500")
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
                    className="mt-3 rounded-lg border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-700 transition hover:bg-teal-50 disabled:opacity-50"
                  >
                    {codesApproved ? "Codes approved ✓" : "Approve all codes"}
                  </button>
                )}
              </Card>
            )}

            {/* 5. Referral */}
            {latestNote && (
              <Card
                id="step-referral"
                title="Referral letter"
                status={!referral ? "pending" : referralApproved ? "approved" : "review"}
                statusLabel={!referral ? "Not generated" : referralApproved ? "Approved" : "Awaiting approval"}
              >
                <button
                  onClick={() => run("referral", () => generateReferral(id))}
                  disabled={busy !== null}
                  className="rounded-lg bg-ink-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink-800 disabled:opacity-60"
                >
                  {busy === "referral" ? "Generating…" : referral ? "Regenerate referral" : "Generate referral"}
                </button>
                {referral && (
                  <>
                    <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-ink-200 bg-ink-50 p-3 text-sm text-ink-700">
                      {referral.letter_text}
                    </pre>
                    <button
                      onClick={() => run("approveReferral", () => approveReferral(id, approver))}
                      disabled={busy !== null || referralApproved}
                      className="mt-3 rounded-lg border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-700 transition hover:bg-teal-50 disabled:opacity-50"
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
                id="step-export"
                title="Approve & export to FHIR"
                status={exported ? "done" : "pending"}
                statusLabel={exported ? "Exported" : "Awaiting approval + export"}
              >
                <p className="text-sm text-ink-600">
                  Export is gated: the note{codes.length > 0 ? ", codes" : ""}
                  {referral ? ", and referral" : ""} must each be approved first.
                </p>
                <button
                  onClick={() => run("export", () => exportFhir(id))}
                  disabled={busy !== null}
                  className="mt-3 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:opacity-60"
                >
                  {busy === "export" ? "Exporting…" : "Export to FHIR"}
                </button>
                {exports.length > 0 && (
                  <ul className="mt-3 space-y-2">
                    {exports.map((e) => (
                      <li key={e.id} className="rounded-xl border border-ink-200 bg-white p-3">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-medium text-ink-900">
                            {e.resource_type}{" "}
                            <span className="rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-600">
                              FHIR {e.fhir_version}
                            </span>
                          </p>
                          <button
                            onClick={() => downloadJson(`${e.resource_type}-${e.id}.json`, e.json_text)}
                            className="shrink-0 rounded-lg border border-ink-300 px-3 py-1 text-xs font-medium text-ink-700 transition hover:bg-ink-50"
                          >
                            Download
                          </button>
                        </div>
                        <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-ink-50 p-2 font-mono text-xs text-ink-600">
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
                <p className="text-sm text-ink-400">No events yet.</p>
              ) : (
                <ul>
                  {audit.map((a, i) => (
                    <li key={a.id} className="relative flex gap-3 pb-4 last:pb-0">
                      {i < audit.length - 1 && (
                        <span
                          className="absolute left-[4px] top-3 h-full w-px bg-ink-100"
                          aria-hidden="true"
                        />
                      )}
                      <span
                        className={
                          "relative mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full " +
                          (a.actor === "user" ? "bg-teal-500" : "bg-ink-300")
                        }
                      />
                      <div className="min-w-0">
                        <p className="text-sm text-ink-800">
                          <span className="font-medium">{a.action.replace(/_/g, " ")}</span>
                          {a.actor_name ? ` · ${a.actor_name}` : ""}
                        </p>
                        <p className="font-mono text-xs text-ink-400">
                          {new Date(a.created_at).toLocaleString()}
                          {a.artifact_type ? ` · ${a.artifact_type}` : ""}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

type RailStep = { key: string; label: string; done: boolean };

function ChartRail({ steps }: { steps: RailStep[] }) {
  const currentIdx = steps.findIndex((s) => !s.done);
  return (
    <nav aria-label="Encounter progress" className="hidden lg:block">
      <ol className="sticky top-24">
        {steps.map((s, i) => {
          const isCurrent = i === currentIdx;
          const isLast = i === steps.length - 1;
          return (
            <li key={s.key} className="relative pb-8 last:pb-0">
              {!isLast && (
                <span
                  className={
                    "absolute left-[15px] top-8 h-full w-px " + (s.done ? "bg-teal-400" : "bg-ink-200")
                  }
                  aria-hidden="true"
                />
              )}
              <a href={`#${s.key}`} className="group flex items-start gap-3">
                <span
                  className={
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-serif text-xs font-semibold ring-4 ring-ink-25 transition " +
                    (s.done
                      ? "bg-teal-600 text-white"
                      : isCurrent
                        ? "bg-white text-teal-700 ring-2 ring-inset ring-teal-500"
                        : "bg-ink-100 text-ink-400")
                  }
                >
                  {s.done ? "✓" : i + 1}
                </span>
                <span
                  className={
                    "mt-1.5 text-sm font-medium transition group-hover:text-teal-700 " +
                    (s.done || isCurrent ? "text-ink-800" : "text-ink-400")
                  }
                >
                  {s.label}
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function MobileRail({ steps }: { steps: RailStep[] }) {
  return (
    <ol className="mb-6 flex flex-wrap items-center gap-2 rounded-xl border border-ink-200 bg-white px-4 py-3 lg:hidden">
      {steps.map((s, i) => (
        <li key={s.key} className="flex items-center gap-2">
          <a href={`#${s.key}`} className="flex items-center gap-2">
            <span
              className={
                "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold " +
                (s.done ? "bg-teal-600 text-white" : "bg-ink-100 text-ink-400")
              }
            >
              {s.done ? "✓" : i + 1}
            </span>
            <span className={"text-sm " + (s.done ? "text-ink-800" : "text-ink-400")}>{s.label}</span>
          </a>
          {i < steps.length - 1 && <span className="text-ink-300">→</span>}
        </li>
      ))}
    </ol>
  );
}

function Card({
  id,
  title,
  status,
  statusLabel,
  children,
}: {
  id?: string;
  title: string;
  status: "pending" | "review" | "approved" | "done";
  statusLabel: string;
  children: React.ReactNode;
}) {
  const pill = {
    pending: "bg-ink-100 text-ink-500",
    review: "bg-ember-100 text-ember-700",
    approved: "bg-teal-100 text-teal-700",
    done: "bg-teal-100 text-teal-700",
  }[status];
  return (
    <section
      id={id}
      className="scroll-mt-24 rounded-2xl border border-ink-200 bg-white p-5 shadow-[0_1px_2px_rgba(24,36,32,0.03)]"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-serif text-base font-semibold text-ink-900">{title}</h2>
        <span className={"rounded-full px-2.5 py-1 text-xs font-medium " + pill}>{statusLabel}</span>
      </div>
      {children}
    </section>
  );
}
