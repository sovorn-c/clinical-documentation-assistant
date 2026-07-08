// Thin fetch wrapper. The JWT is stored in localStorage (demo only — Phase 6
// hardens storage). All calls go same-origin via the Next.js rewrite to the
// FastAPI backend, so there are no CORS concerns in the browser.

import type {
  AuditEntry,
  CodeSuggestion,
  Encounter,
  FhirExport,
  Note,
  Patient,
  Referral,
  Token,
  Transcript,
  User,
} from "./types";

const TOKEN_KEY = "clin_doc_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, "Unauthorized");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body === "object" && body ? JSON.stringify(body.detail ?? body) : detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- auth ---
export const login = (username: string, password: string) => {
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  return request<Token>("/api/auth/login", {
    method: "POST",
    body: form,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
};

export const me = () => request<User>("/api/auth/me");

// --- patients ---
export const listPatients = () => request<Patient[]>("/api/patients");
export const createPatient = (body: {
  patient_ref: string;
  display_name?: string | null;
  fhir_bundle_path?: string | null;
}) => request<Patient>("/api/patients", { method: "POST", body: JSON.stringify(body) });

// --- encounters ---
export const createEncounter = (body: {
  patient_id: string;
  encounter_ref: string;
  audio_path?: string | null;
}) => request<Encounter>("/api/encounters", { method: "POST", body: JSON.stringify(body) });

export const getEncounter = (id: string) => request<Encounter>(`/api/encounters/${id}`);

export const uploadAudio = (id: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<Encounter>(`/api/encounters/${id}/audio`, {
    method: "POST",
    body: form,
    // NOTE: do not set Content-Type — the browser sets the multipart boundary.
  });
};
export const getTranscript = (id: string) =>
  request<Transcript>(`/api/encounters/${id}/transcript`);
export const getNote = (id: string) => request<Note>(`/api/encounters/${id}/note`);
export const getNoteVersions = (id: string) =>
  request<Note[]>(`/api/encounters/${id}/notes`);

export const generateNote = (id: string) =>
  request<Note>(`/api/encounters/${id}/generate-note`, { method: "POST" });

export const editNote = (id: string, note: Record<string, unknown>) =>
  request<Note>(`/api/encounters/${id}/note`, {
    method: "PUT",
    body: JSON.stringify({ note }),
  });

// --- codes ---
export const suggestCodes = (id: string) =>
  request<CodeSuggestion[]>(`/api/encounters/${id}/suggest-codes`, { method: "POST" });
export const listCodes = (id: string) => request<CodeSuggestion[]>(`/api/encounters/${id}/codes`);
export const approveCodes = (id: string, approver: string) =>
  request<void>(`/api/encounters/${id}/approve-codes`, {
    method: "POST",
    body: JSON.stringify({ approver_name: approver, approver_role: "clinician" }),
  });

// --- referral ---
export const generateReferral = (id: string) =>
  request<Referral>(`/api/encounters/${id}/generate-referral`, { method: "POST" });
export const getReferral = (id: string) =>
  request<Referral>(`/api/encounters/${id}/referral`);
export const approveReferral = (id: string, approver: string) =>
  request<void>(`/api/encounters/${id}/approve-referral`, {
    method: "POST",
    body: JSON.stringify({ approver_name: approver, approver_role: "clinician" }),
  });

// --- approvals + export ---
export const approveNote = (id: string, approver: string) =>
  request<{ note_id: string; approved: boolean }>(`/api/encounters/${id}/approve-note`, {
    method: "POST",
    body: JSON.stringify({ approver_name: approver, approver_role: "clinician" }),
  });
export const exportFhir = (id: string) =>
  request<FhirExport[]>(`/api/encounters/${id}/export-fhir`, { method: "POST" });
export const listExports = (id: string) =>
  request<FhirExport[]>(`/api/encounters/${id}/exports`);
export const listAudit = (id: string) =>
  request<AuditEntry[]>(`/api/encounters/${id}/audit`);

// --- summaries ---
export const summarizePatient = (id: string) =>
  request<Record<string, unknown>>(`/api/patients/${id}/summarize`, { method: "POST" });
