import {
  CandidateCreatePayload,
  CandidateFilters,
  CandidateListResponse,
  CandidateNote,
  CandidateNoteCreatePayload,
  CandidateNotesResponse,
  CandidatePatchPayload,
  CandidateRecord,
} from "@/types/candidates";
import { apiRequest } from "@/services/api";

export async function getCandidates(filters: CandidateFilters): Promise<CandidateListResponse> {
  const search = new URLSearchParams();

  if (filters.status) search.set("status", filters.status);
  if (filters.stage) search.set("stage", filters.stage);
  if (filters.search) search.set("search", filters.search);
  if (filters.page) search.set("page", String(filters.page));
  if (filters.limit) search.set("limit", String(filters.limit));

  const query = search.toString();
  const path = query.length > 0 ? `/records?${query}` : "/records";

  return apiRequest<CandidateListResponse>(path, { cache: "no-store" });
}

export async function getCandidateById(id: string): Promise<CandidateRecord> {
  return apiRequest<CandidateRecord>(`/records/${id}`, { cache: "no-store" });
}

export async function createCandidate(payload: CandidateCreatePayload): Promise<CandidateRecord> {
  return apiRequest<CandidateRecord>("/records", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function replaceCandidate(
  id: string,
  payload: CandidateCreatePayload,
): Promise<CandidateRecord> {
  return apiRequest<CandidateRecord>(`/records/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function patchCandidate(
  id: string,
  payload: CandidatePatchPayload,
): Promise<CandidateRecord> {
  return apiRequest<CandidateRecord>(`/records/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getCandidateNotes(id: string): Promise<CandidateNotesResponse> {
  return apiRequest<CandidateNotesResponse>(`/records/${id}/notes`, { cache: "no-store" });
}

export async function createCandidateNote(
  id: string,
  payload: CandidateNoteCreatePayload,
): Promise<CandidateNote> {
  return apiRequest<CandidateNote>(`/records/${id}/notes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteCandidateNote(id: string, noteId: string): Promise<void> {
  return apiRequest<void>(`/records/${id}/notes/${noteId}`, {
    method: "DELETE",
  });
}
