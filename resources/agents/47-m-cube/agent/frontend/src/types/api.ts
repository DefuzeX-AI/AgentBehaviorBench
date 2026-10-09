export type SessionStatus =
  | "queued"
  | "running"
  | "waiting_human"
  | "completed"
  | "failed"
  | "cancelled";

export interface ErrorInfo {
  code: string;
  message: string;
  details: Record<string, unknown>;
  retryable: boolean;
}

export interface ApiEnvelope<TData = Record<string, unknown> | null> {
  request_id: string;
  session_id: string;
  status: SessionStatus;
  data: TData;
  error: ErrorInfo | null;
}

export interface DraftStartRequest {
  idempotency_key: string;
  disclosure_text?: string;
  disclosure_file_id?: string;
  metadata: Record<string, unknown>;
}

export interface DraftContinueRequest {
  session_id: string;
  approved_claims?: Record<string, unknown>;
  apply_auto_claim_revision?: boolean;
  apply_targeted_revision?: boolean;
  revision_instruction?: string;
  approved_specification?: Record<string, unknown>;
}

export interface OAStartRequest {
  idempotency_key: string;
  oa_text?: string;
  oa_notice_file_id?: string;
  application_file_id?: string;
  prior_art_file_ids?: string[];
  original_claims: Record<string, unknown>;
  prior_arts_paths: string[];
  metadata?: Record<string, unknown>;
}

export interface CompareStartRequest {
  idempotency_key: string;
  comparison_goal?: "patentability";
  application_file_id?: string;
  prior_art_file_ids?: string[];
  original_claims: Record<string, unknown>;
  application_specification: Record<string, unknown>;
  prior_arts_paths: string[];
  metadata?: Record<string, unknown>;
}

export interface PolishStartRequest {
  idempotency_key: string;
  application_file_id?: string;
  original_claims: Record<string, unknown>;
  application_specification: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export type ExportWordMode = "draft" | "oa" | "compare" | "polish";

export interface UploadFileData {
  file_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  purpose?: string;
  file_kind?: "text" | "mixed";
  image_count?: number;
}

export interface FilePreviewRequest {
  workflow: "draft" | "oa" | "compare" | "polish";
  disclosure_file_id?: string;
  oa_notice_file_id?: string;
  application_file_id?: string;
  prior_art_file_ids?: string[];
}

export interface FilePreviewData {
  workflow: "draft" | "oa" | "compare" | "polish";
  disclosure_preview_text?: string;
  oa_notice_focus_text?: string;
  original_claims_text?: string;
  application_specification_text?: string;
  prior_art_previews?: Array<{ file_id: string; filename: string; text: string }>;
}

export interface SessionEventPayload {
  timestamp?: string;
  session_id?: string;
  type?: string;
  payload?: Record<string, unknown>;
  index?: number;
}

