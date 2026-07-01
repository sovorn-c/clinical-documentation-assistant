# Clinical Documentation Assistant (B1) — Execution Plan

> **Tier:** 🔴 Big · **Est. effort:** 2–4 weeks · **Status:** 🔴 Not started
> **Reuses:** M1 (scribe) + S2 (de-identifier) + S3 (coder) + S1 (summarizer, ships `clinical_core`)
> **Recommended flagship — the "I can build your whole product" piece.**
>
> _Revised 2026-07-01: verified upstream interfaces against actual source (§7), mapped pipeline
> wiring gaps (§8), reordered Phase 1/2 for dependency correctness, time-boxed every phase, and
> flagged two deployment-blocking risks (§11) that weren't visible from the original brief alone._
>
> _Second pass, same day: checked tech-stack currency against mid-2026 state. S3's cloud LLM
> default (`claude-sonnet-4-5`) is stale — two generations behind current; S2's default
> (`claude-haiku-4-5`) is still current. Found a concrete cross-platform replacement for M1's
> Apple-Silicon-only ASR, upgrading §11's ASR risk from "pick a fallback" to "pick a real swap"._

---

## 1. Overview
A deployed, full-stack product that takes a consultation from audio to finished documentation:
**record → transcribe → SOAP note → suggested codes → referral letter → FHIR write-back**, all behind
an edit-and-approve clinician UI with an audit trail. Integrates three earlier projects into one
coherent application.

## 2. Why This Project (Market Context)
Combines the hottest feature (ambient scribe) with the most sellable automations (coding, referral
generation) into a deployable product. Demonstrates you can ship a real application — not just a
notebook — which is what converts startup and clinic conversations into contracts.

## 3. Success Criteria
- [ ] Deployed app reachable via URL (demo environment, synthetic data only).
- [ ] Full pipeline works end-to-end with human approval gates.
- [ ] Persists encounters/notes/codes; full audit log.
- [ ] FHIR export validated; patient context read from FHIR.
- [ ] Auth + basic security; documented architecture.

## 4. Tech Stack
Backend: FastAPI, Postgres, SQLModel/SQLAlchemy. Frontend: React/Next.js + Tailwind. Engines: M1
scribe, S2 de-identifier, S3 coder, S1 summarizer — imported directly as local packages, not
reimplemented (exact entrypoints in §7). Infra: Docker, deploy on Render/Railway/Fly.io. Auth: simple
JWT. `fhir.resources>=8.0` (the version pin matters — R4 vs R5 — see §11).

## 5. Data Source
Synthea patients for context; mock/synthetic consult audio. **No real PHI.** PHI de-identifier (S2)
applied to transcripts before they cross into any cloud LLM call — see §8 for exactly where.

## 6. Prerequisites & Dependencies
- **M1, S2, S3, S1 confirmed complete and independently importable** — verified by direct source
  inspection on 2026-07-01; exact entrypoints in §7. All four are clean enough to import as-is; the
  work in this project is wiring (§8), not rework.
- `clinical_core` — real and fully implemented (FHIR load/normalize, LLM wrapper, settings, eval),
  but it ships *inside* the `fhir-clinical-summarizer` (S1) package rather than as its own standalone
  dependency. Depend on S1 to get it — see §7.
- Cloud account for deployment (Render/Railway/Fly.io) — before committing to a provider, confirm it
  can either run M1's local ASR/LLM runtime as-is, or budget time to swap it for a cloud-compatible
  equivalent. See §11.

## 7. Upstream Package Interfaces
Confirmed by direct inspection of each repo (2026-07-01). All four are cleanly importable as-is — no
rework needed, only wiring (§8).

### M1 — `ai-ambient-scribe` (audio → SOAP note → FHIR DocumentReference)
- **Install:** `uv add --path ../ai-ambient-scribe`
- **Entry:** `scribe.composition.build_scribe(cfg) -> Scribe`, then:
  - `Scribe.generateDraft(audio: Audio, ctx: PatientContext) -> Draft` (side-effect-free)
  - `Scribe.approveAndExport(edited: EditedDraft, approver: Approver) -> DocumentRef` — FHIR export
    is gated behind approval; there's no code path that bypasses it.
- **Input:** `Audio(source="file", path="...", sample_rate=16000, channels=1)` — wraps a `.wav` file.
- **Output:** `Draft.note` is a `SOAPNote`/`GroundedNote` — four lists
  (`subjective/objective/assessment/plan`) of `Claim(text, citations: list[SpanRef])`. Every claim is
  grounded to a transcript span. `approveAndExport` returns `DocumentRef(resource: dict, json_text:
  str)` — a validated FHIR **R5** `DocumentReference` with the SOAP note base64-embedded.
- **Key types:** `from scribe.domain.types import Audio, PatientContext, Draft, EditedDraft, Approver, DocumentRef`
- **Runtime:** 100% local/offline — `mlx-whisper` (transcription) + `ollama` serving Qwen2.5-7B (note
  generation) + `sherpa-onnx` (diarization). No cloud LLM calls.
- ⚠️ **Deployment gotcha:** `mlx-whisper` is Apple-Silicon-only (Apple MLX/Metal). It will not run on
  a standard Linux container (Render/Railway/Fly.io). Checked mid-2026: `faster-whisper`
  (CTranslate2, CPU-friendly, cross-platform) is the practical drop-in swap for a cloud demo — same
  Whisper weights, no Apple dependency. This is a Phase 0 decision, not a Phase 5 surprise — see §11.

### S2 — `phi-deidentifier` (transcript/note text → redacted text + PHI spans)
- **Install:** `uv add --path ../phi-deidentifier`
- **Entry:** `from phi.deidentify import deidentify; deidentify(text: str, config: DeidConfig | None = None) -> DeidResult`
- **Input:** plain `str`, any shape (transcript, note text, FHIR-extracted text). Tuned via
  `DeidConfig(strategy="mask"|"hash"|"surrogate", use_rules=True, use_ner=True, use_llm=False, ...)`.
- **Output:** `DeidResult(redacted_text: str, spans: list[PHISpan], audit: list[AuditEntry])` across
  14 entity types (person, location, org, date, age, phone, email, MRN, NHI/Medicare/IHI, etc.).
  Deterministic and idempotent — safe to run twice.
- **Runtime:** local rules + spaCy/Presidio NER by default (`use_llm=False`). Optional cloud LLM
  second pass via LiteLLM if `use_llm=True` — leave it off unless you have a specific reason (see §11).
- **Gotcha:** `hash`/`surrogate` strategies need a `PHI_HASH_KEY` env var; `mask` needs nothing extra
  — simplest default for B1.

### S3 — `auto-medical-coder` (note text → ranked ICD-10-CM codes)
- **Install:** `uv add --path ../auto-medical-coder`
- **Entry:** `from auto_medical_coder import code; code(note: str, *, note_id: str | None = None) -> list[CodeSuggestion]`
- **Input:** plain `str` — any clinical note text, no SOAP-specific shape required.
- **Output:** `CodeSuggestion(code, description, confidence: float, evidence: EvidenceSpan, rank:
  int)`. Zero-hallucination by construction — RAG-retrieves candidates from a real ICD-10-CM
  catalogue (~75k codes) before the LLM ranks/selects, and every `evidence.quote` is verified
  verbatim against the input note (`note[start:end] == quote`).
- **Runtime:** cloud LLM via LiteLLM (`MODEL`/`API_KEY` env vars, defaults to Claude), plus a local
  sentence-transformers + Chroma index.
- ⚠️ **Stale default (checked mid-2026):** S3's `.env` defaults `MODEL` to
  `anthropic/claude-sonnet-4-5` — two generations behind current (`claude-sonnet-5` is now the
  recommended Sonnet-tier model). Not a blocker, the ID still works, but bump it before Phase 5 so
  the demo isn't running on a superseded model. S2's default (`claude-haiku-4-5`) is already
  current — no change needed there.
- ⚠️ **First-run cost:** catalogue + embedding index must be built once (`python -m
  auto_medical_coder.catalogue` then `.index`, a few minutes) — bake into the Docker image build, not
  into request-time latency.
- **Scope:** ICD-10-CM diagnosis codes only. No SNOMED, no procedure codes. Suggestions only — a
  human coder confirms before anything is billed.

### S1 — `fhir-clinical-summarizer` (FHIR bundle → clinician summary) + `clinical_core`
- **Install:** `uv add --path ../fhir-clinical-summarizer` — this wheel ships **two** importable
  top-level packages: `summarizer` and `clinical_core`.
- **Entry:** `from summarizer.pipeline import summarize; summarize(record: PatientRecord) -> Summary`
- **Context loading (this is what Phase 4 needs):**
  `from clinical_core.fhir import load_bundle; record = load_bundle("bundle.json") -> PatientRecord`
- **Output:** `Summary(one_liner, sections: list[Section]` — five fixed sections: Problems,
  Medications, Recent Encounters, Key Results, Allergies — `, .to_markdown(), faithfulness:
  FaithfulnessReport)`. Every bullet carries `source_refs` back to the originating FHIR resource.
- ⚠️ **`clinical_core` status — corrects §6:** it's real and fully implemented (`fhir/`, `llm/`,
  `config/`, `eval/` submodules), but currently lives *inside* `fhir-clinical-summarizer/src/`, not as
  its own standalone sibling package. **Decision for Phase 0:** depend on `fhir-clinical-summarizer`
  directly and import `clinical_core.*` from it — do not re-extract it into a new package under time
  pressure; that's exactly the kind of scope creep §11 warns against.
- **Note:** only S1 uses `clinical_core`. S2 and S3 each have their own independent LiteLLM wrapper,
  and M1 doesn't touch cloud LLMs at all. The "shared foundation" is real but partially adopted —
  don't try to retrofit unity across all four in this project.

## 8. Pipeline Wiring — where the glue code actually goes
Mapping the plan's headline flow (record → transcribe → de-identify → SOAP note → codes → referral →
FHIR) onto the four engines in §7 surfaces four points that are **not** covered by existing code —
genuinely new work for B1's backend, not integration:

1. **Where PHI de-identification actually plugs in.** The brief says S2 is "applied to transcripts,"
   but M1's `generateDraft()` is one call that does transcription → note-drafting internally via a
   local LLM — there's no exposed hook between the two steps. Recommended: don't fight that boundary.
   Run S2's `deidentify()` on the transcript/note text specifically before it crosses into any call
   that leaves the trust boundary — S3's `code()` and the net-new referral-letter generation both hit
   a cloud LLM. Keep the clinician-facing copy (what's stored as the canonical encounter and shown in
   the UI) un-redacted — a clinician needs real identifiers to chart correctly. Confirm this in Phase
   0; it determines what the audit log actually stores.
2. **SOAPNote → plain text, before coding.** S3's `code()` takes a flat string; M1's `Draft.note` is
   a structured `SOAPNote` (four claim lists). Write a small adapter that flattens
   `edited.note.all_claims()` into text before calling `auto_medical_coder.code()`.
3. **Referral letter generation is net-new.** None of M1/S2/S3/S1 generate a referral letter. Build
   it as its own LLM call in B1's backend, reusing `clinical_core.llm.LLMClient` (from S1) for the
   provider-agnostic wrapper rather than adding a fifth LLM-calling pattern to the app.
4. **Codes → FHIR `Condition`/`Claim` resources is net-new.** S3 outputs `CodeSuggestion` Pydantic
   objects, not FHIR resources. M1's `FhirExporter` only emits `DocumentReference` for the note
   itself. Phase 4 needs its own mapping from `CodeSuggestion` → `Condition`/`Claim`, validated the
   same way M1 validates its `DocumentReference` — and against the same FHIR version decided in
   Phase 0 (M1 emits R5; the original brief assumed R4 — see §11).

Everything else — transcription, note drafting, code suggestion, patient-context loading — is pure
reuse; call the entrypoints in §7 and do not reimplement them.

## 9. Execution Phases

### Phase 0 — Architecture & Monorepo
**Time-box:** 1–2 days
**Objectives:** Integration design + scaffold.
**Key tasks:**
- [ ] System design doc + architecture diagram (services, data flow, trust boundaries).
- [ ] Monorepo: `backend/`, `frontend/`, `packages/` (scribe, coder, summarizer), `infra/`.
- [ ] Add M1/S2/S3/S1 as local path dependencies (§7) and smoke-test one call to each
      (`generateDraft` with fake audio, `deidentify()` on a sample string, `code()` on a sample note,
      `summarize()` on a fixture bundle).
- [ ] **Decide the transcription/deployment strategy** (§11): swap M1's `mlx-whisper` for
      `faster-whisper` (same weights, CPU-friendly, cross-platform — the recommended default) so the
      cloud demo does real transcription, or fall back to pre-baked demo audio→transcript pairs only
      if the swap doesn't fit the time-box. This gates Phase 5 — do not defer it.
- [ ] **Decide the FHIR version** the whole app targets (M1 emits R5; the original brief assumed R4
      — §8 point 4). Pin one version everywhere.
**Deliverable:** Repo skeleton + design doc + working imports of all four engines.
**Acceptance:** Engines importable and individually callable; design and both decisions above are
reviewed and written down, not left implicit.

### Phase 1 — Data Layer & Audit
**Time-box:** 1–2 days
**Objectives:** Persistence + traceability, built first because the API in Phase 2 depends on it.
**Key tasks:**
- [ ] Postgres schema: patients(ref), encounters, transcripts, notes, codes, referrals, approvals —
      shaped to hold the actual return types from §7 (`Draft`/`SOAPNote`, `DeidResult`,
      `CodeSuggestion`, `Summary`, `DocumentRef`), not a generic guess.
- [ ] Append-only audit log (who/what/when, incl. AI-vs-human edits, and de-id events per §8 point 1).
**Deliverable:** Migrations + repositories.
**Acceptance:** Every state change audited; schema round-trips each Pydantic model from §7 without
lossy conversion.

### Phase 2 — Backend API
**Time-box:** 2–4 days
**Objectives:** Orchestrate the pipeline over the Phase 1 schema.
**Key tasks:**
- [ ] Endpoints: upload/transcribe, generate-note, suggest-codes, generate-referral, summarize,
      fhir-export — each a thin wrapper over the §7 entrypoints.
- [ ] Apply S2's `deidentify()` to the transcript/note copy before it crosses into `suggest-codes` or
      `generate-referral` (§8 point 1) — not to the clinician-facing canonical copy.
- [ ] Note→text adapter ahead of suggest-codes (§8 point 2) — flatten `SOAPNote.all_claims()` before
      calling `auto_medical_coder.code()`.
- [ ] Referral-letter generation (§8 point 3) — net-new LLM call; reuse `clinical_core.llm.LLMClient`
      from S1 rather than adding a fifth LLM-calling pattern.
- [ ] Pipeline orchestration with explicit human-approval checkpoints — extend M1's
      `Draft → EditedDraft → ApprovedNote` gating pattern to codes and referral, so nothing reaches
      `fhir-export` without a human approval record in the audit log.
- [ ] Auth + request validation.
**Deliverable:** Working API.
**Acceptance:** Full flow exercised via API tests.

### Phase 3 — Frontend
**Time-box:** 3–5 days
**Objectives:** The clinician experience.
**Key tasks:**
- [ ] Flow: select patient → record/upload → review transcript → edit SOAP note → review codes →
      generate/edit referral → approve → export.
- [ ] Clear draft/approved states; diff of AI output vs human edits.
**Deliverable:** Frontend app.
**Acceptance:** A non-technical user completes the flow unaided.

### Phase 4 — FHIR Integration
**Time-box:** 2–3 days
**Objectives:** Standards-based I/O, reusing what M1/S1 already validate rather than reimplementing
FHIR handling.
**Key tasks:**
- [ ] Read patient/encounter context from FHIR via `clinical_core.fhir.load_bundle` (§7, S1) — reuse
      as-is.
- [ ] Write note as `DocumentReference` via M1's `FhirExporter`/`approveAndExport` (§7, M1) — reuse
      as-is; do not hand-roll a second `DocumentReference` builder.
- [ ] Net-new: map approved `CodeSuggestion` list → `Condition`/`Claim` resources (§8 point 4) —
      nothing upstream produces this.
- [ ] Validate everything against the FHIR version decided in Phase 0.
**Deliverable:** Bidirectional FHIR layer.
**Acceptance:** Exports validate; context loads from sandbox.

### Phase 5 — Deployment
**Time-box:** 1–3 days (longer if Phase 0 decided to swap M1's ASR backend)
**Objectives:** Live demo.
**Key tasks:**
- [ ] Dockerize; env/secrets management; managed Postgres.
- [ ] Execute the transcription-strategy decision from Phase 0: either bundle a Linux-compatible ASR
      swap for M1's transcription step, or wire the demo to pre-baked audio→transcript pairs.
- [ ] Bake S3's catalogue + embedding index build into the image build step, not request-time (§7 —
      first-run cost is a few minutes; don't pay it per request).
- [ ] Deploy to cloud; seed synthetic demo data; basic rate limiting/logging.
**Deliverable:** Public demo URL.
**Acceptance:** App reachable + stable with seeded data.

### Phase 6 — Security, Polish & Demo
**Time-box:** 2–3 days
**Objectives:** Production-feel + presentation.
**Key tasks:**
- [ ] Security pass (authz checks, input sanitisation, secrets hygiene, dependency audit).
- [ ] Performance polish; error states; "synthetic data only" banner.
- [ ] README (architecture diagram, walkthrough), recorded demo video.
**Deliverable:** Hardened app + demo video.
**Acceptance:** Security checklist complete; demo recorded.

**Total time-box: ~12–22 working days (≈2.5–4.5 weeks)** — close to the original estimate. If any
phase blows through its high end, cut scope rather than extend the deadline (§11).

## 10. Portfolio Deliverables
Live demo URL + walkthrough video + architecture diagram + system-design doc. LinkedIn angle:
*"I built and deployed a full ambient clinical documentation product — audio to FHIR, clinician in the
loop, end to end."*

## 11. Risks & Notes
- **Scope creep is the main risk** — lock the happy path first, polish second.
- Demo must visibly use synthetic data only; never expose anything resembling real PHI.
- **Reuse M1/S2/S3/S1 as-is; resist rewriting them.** All four are already clean, tested, importable
  packages (§7) — the work here is wiring plus the four net-new pieces in §8, not re-engineering.
- **M1's ASR runtime is Apple-Silicon-only.** `mlx-whisper` needs Apple MLX/Metal and will not run on
  a standard Linux PaaS container (Render/Railway/Fly.io). Checked mid-2026: swap it for
  `faster-whisper` (CTranslate2, CPU-friendly, cross-platform, same Whisper weights) — a real fix,
  not just a fallback, so the cloud demo can do live transcription. Decide in Phase 0; ship
  pre-baked audio→transcript pairs only if the swap doesn't fit the time-box. The same question
  applies to `ollama` serving M1's note-generation LLM — confirm the target host can run it, or swap
  that piece too.
- **S3's cloud LLM default is a superseded model.** `.env` defaults `MODEL` to
  `anthropic/claude-sonnet-4-5` — still functional, but two generations behind current
  (`claude-sonnet-5`). Bump it before Phase 5; S1's LLM default wasn't confirmed either way by
  inspection — verify before deploying.
- **FHIR version mismatch.** M1 emits FHIR **R5** `DocumentReference` (`fhir.resources>=8.0`); the
  original brief assumed R4 (typical for Synthea/HAPI sandboxes). Pick one version in Phase 0 and
  apply it consistently, rather than discovering the mismatch during Phase 4 validation.
- **`clinical_core` is a partial foundation, not a unified one.** Only S1 uses it; S2 and S3 each have
  their own independent LiteLLM wrapper, and M1 doesn't call a cloud LLM at all. Don't retrofit
  consistency across the four during B1 — that's scope creep on someone else's finished work.
- S2's optional LLM second pass (`use_llm=True`) sends text to a third-party API — leave it off (the
  default) unless a specific recall gap on your demo fixtures justifies it. Don't enable it reflexively.

## 12. Definition of Done
Deployed, authenticated, audited app covering audio→FHIR with approval gates; security pass done;
demo video + design doc + README published.
