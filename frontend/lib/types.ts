// Types mirroring the backend Pydantic schemas (clin_doc/schemas.py) and the
// upstream SOAPNote shape (scribe.domain.types). Kept loose where the backend
// returns nested engine objects as JSON.

export type Token = { access_token: string; token_type: string };

export type User = {
  id: string;
  username: string;
  display_name: string | null;
  role: string;
};

export type Patient = {
  id: string;
  patient_ref: string;
  display_name: string | null;
  fhir_bundle_path: string | null;
};

export type EncounterStatus =
  | "audio_uploaded"
  | "note_drafted"
  | "note_edited"
  | "codes_suggested"
  | "referral_generated"
  | "approved"
  | "exported";

export type Encounter = {
  id: string;
  patient_id: string;
  encounter_ref: string;
  status: EncounterStatus;
  audio_path: string | null;
  created_at: string;
};

export type SpanRef = {
  utterance_id: string;
  char_span?: [number, number] | null;
};

export type Claim = { text: string; citations?: SpanRef[] };

export type SOAPNote = {
  subjective: Claim[];
  objective: Claim[];
  assessment: Claim[];
  plan: Claim[];
};

export type Utterance = {
  id: string;
  role: "CLINICIAN" | "PATIENT" | "UNKNOWN";
  text: string;
  time_span?: { start: number; end: number };
  speaker_id?: string;
};

export type Transcript = {
  id: string;
  encounter_id: string;
  utterances: Utterance[];
  transcript_text: string | null;
  asr_id: string | null;
  diarizer_id: string | null;
};

export type Note = {
  id: string;
  encounter_id: string;
  version: number;
  source: "ai" | "human";
  note: SOAPNote;
  provenance: Record<string, unknown> | null;
  draft_id: string | null;
  created_at: string;
};

export type CodeSuggestion = {
  id: string;
  code: string;
  description: string | null;
  confidence: number;
  rank: number;
  evidence: Record<string, unknown>;
  approved: boolean;
};

export type Referral = {
  id: string;
  encounter_id: string;
  letter_text: string;
  model: string | null;
  approved: boolean;
  created_at: string;
};

export type FhirExport = {
  id: string;
  resource_type: string;
  fhir_version: string;
  resource: Record<string, unknown>;
  json_text: string;
  created_at: string;
};

export type AuditEntry = {
  id: string;
  encounter_id: string | null;
  actor: "system" | "user";
  actor_name: string | null;
  action: string;
  artifact_type: string | null;
  artifact_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
  created_at: string;
};

export const SOAP_SECTIONS = ["subjective", "objective", "assessment", "plan"] as const;
export type SectionKey = (typeof SOAP_SECTIONS)[number];
