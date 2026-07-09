export type CandidateStatus = "received" | "in_progress" | "selected" | "discarded";

export type CandidateStage =
  | "pending"
  | "review"
  | "personal_interview"
  | "technical_interview"
  | "offer_presented";

export interface CandidateNote {
  id: string;
  record_id: string;
  content: string;
  created_at: string;
}

export interface CandidateRecord {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  status: CandidateStatus;
  stage: CandidateStage;
  experience_years: number;
  notes_count: number;
  applied_at: string;
  updated_at: string;
}

export interface CandidateRecordWithNotesPreview extends CandidateRecord {
  notes?: CandidateNote[];
}

export interface CandidateListResponse {
  total: number;
  page: number;
  limit: number;
  data: CandidateRecordWithNotesPreview[];
}

export interface CandidateNotesResponse {
  data: CandidateNote[];
  meta: {
    total: number;
  };
}

export interface CandidateFilters {
  status?: CandidateStatus | "";
  stage?: CandidateStage | "";
  search?: string;
  page?: number;
  limit?: number;
}

export interface CandidateCreatePayload {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url?: string | null;
  cv_url?: string | null;
  experience_years: number;
}

export interface CandidatePatchPayload {
  status?: CandidateStatus;
  stage?: CandidateStage;
}

export interface CandidateNoteCreatePayload {
  content: string;
}

export interface ApiErrorResponse {
  error?: string;
  detail?: string | { msg?: string }[];
}
