"use client";

import { useEffect, useMemo, useState } from "react";
import type { Note, SOAPNote, SectionKey } from "@/lib/types";
import { SOAP_SECTIONS } from "@/lib/types";
import { diffLines, flattenNote } from "@/lib/diff";

type SectionText = Record<SectionKey, string>;

function noteToText(note: SOAPNote): SectionText {
  const out = {} as SectionText;
  for (const k of SOAP_SECTIONS) {
    out[k] = note[k].map((c) => c.text).join("\n");
  }
  return out;
}

function textToNote(text: SectionText): SOAPNote {
  const out = {} as SOAPNote;
  for (const k of SOAP_SECTIONS) {
    out[k] = text[k]
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((t) => ({ text: t, citations: [] as [] }));
  }
  return out;
}

const LABELS: Record<SectionKey, string> = {
  subjective: "Subjective",
  objective: "Objective",
  assessment: "Assessment",
  plan: "Plan",
};

export function SoapEditor({
  note,
  aiNote,
  saving,
  onSave,
}: {
  note: Note;
  aiNote: Note | null;
  saving: boolean;
  onSave: (note: SOAPNote) => void;
}) {
  const [text, setText] = useState<SectionText>(() => noteToText(note.note));
  const [showDiff, setShowDiff] = useState(false);

  // Re-sync when the note version changes (e.g. after save returns the new version).
  useEffect(() => {
    setText(noteToText(note.note));
  }, [note.id, note.version]);

  const currentNote = useMemo(() => textToNote(text), [text]);
  const diff = useMemo(() => {
    if (!aiNote) return null;
    return diffLines(flattenNote(aiNote.note), flattenNote(currentNote));
  }, [aiNote, currentNote]);

  const dirty = JSON.stringify(currentNote) !== JSON.stringify(note.note);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">SOAP note</h3>
          <p className="text-xs text-slate-500">
            v{note.version} · {note.source === "ai" ? "AI draft" : "human edit"}
            {note.provenance && (
              <>
                {" "}· ASR {String((note.provenance as Record<string, unknown>).asr_id ?? "?")}
              </>
            )}
          </p>
        </div>
        {aiNote && (
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={showDiff}
              onChange={(e) => setShowDiff(e.target.checked)}
              className="rounded border-slate-300"
            />
            Diff vs AI draft
          </label>
        )}
      </div>

      {showDiff && diff ? (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
          <div className="grid grid-cols-2 border-b border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-500">
            <span>AI draft</span>
            <span>Your edits</span>
          </div>
          <pre className="max-h-96 overflow-auto p-3 text-xs leading-relaxed">
            {diff.map((l, i) => (
              <div
                key={i}
                className={
                  l.type === "add"
                    ? "bg-emerald-100/60 text-emerald-800"
                    : l.type === "remove"
                      ? "bg-red-100/60 text-red-800 line-through"
                      : "text-slate-600"
                }
              >
                <span className="select-none pr-2 opacity-60">
                  {l.type === "add" ? "+" : l.type === "remove" ? "−" : " "}
                </span>
                {l.text || "\u00a0"}
              </div>
            ))}
          </pre>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {SOAP_SECTIONS.map((k) => (
            <label key={k} className="block space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {LABELS[k]}
              </span>
              <textarea
                value={text[k]}
                onChange={(e) => setText({ ...text, [k]: e.target.value })}
                rows={4}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </label>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={() => onSave(currentNote)}
          disabled={saving || !dirty || showDiff}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save edit"}
        </button>
        {dirty && <span className="text-xs text-amber-600">Unsaved changes</span>}
        {!dirty && !showDiff && <span className="text-xs text-slate-400">No changes</span>}
      </div>
    </div>
  );
}
