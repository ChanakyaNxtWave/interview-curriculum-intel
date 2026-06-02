import { api, qs } from './client';
import type {
  FeedbackEntry,
  ImprovementSummary,
  TagHistoryEntry,
  TheoryEvalRun,
  TheoryListResponse,
  TheoryPromptVersion,
  TheoryTag,
} from './types';

export interface TheoryListFilters {
  verdict?: string;
  review_status?: string;
  q?: string;
  duration?: string;
  date_from?: string;
  date_to?: string;
  company_name?: string;
  role?: string;
  limit?: number;
  offset?: number;
}

export const fetchTheoryQuestions = (f: TheoryListFilters = {}) =>
  api<TheoryListResponse>(`/api/theory-questions${qs(f)}`);

export const fetchTheoryQuestion = (rowKey: string) =>
  api<TheoryTag>(`/api/theory-questions/${encodeURIComponent(rowKey)}`);

export const tagTheoryQuestion = (rowKey: string) =>
  api<TheoryTag>(`/api/theory-questions/${encodeURIComponent(rowKey)}/tag`, {
    method: 'POST',
  });

export const tagPending = (limit = 50) =>
  api<{ enqueued: number }>(`/api/theory-questions/tag-pending`, {
    method: 'POST',
    body: JSON.stringify({ limit }),
  });

export const tagBatch = (rowKeys: string[]) =>
  api<{ enqueued: number }>(`/api/theory-questions/tag-batch`, {
    method: 'POST',
    body: JSON.stringify({ row_keys: rowKeys }),
  });

export const fetchPendingCount = () =>
  api<{
    pending: number;
    by_type?: { THEORY?: number; CODING?: number };
    total_representatives: number;
  }>(`/api/theory-questions/pending-count`);

export interface ReviewPayload {
  human_required_kps: { source_kp_id: string; confidence?: string; rationale?: string }[];
  human_citations: { content_id: string; kp_id?: string; tag_role?: string }[];
  human_verdict: string;
  review_status: string;
  reviewer_notes?: string;
  gold_rationale?: string;
}

export const submitReview = (rowKey: string, payload: ReviewPayload) =>
  api<{ tag: TheoryTag; eval_source: string }>(
    `/api/theory-questions/${encodeURIComponent(rowKey)}/review`,
    { method: 'PUT', body: JSON.stringify(payload) },
  );

export const fetchEvalRuns = (limit = 50) =>
  api<{ items: TheoryEvalRun[] }>(`/api/evals/runs${qs({ limit })}`);

export const runEvalNow = () =>
  api<{ version: string; metrics: any; devset_size: number }>(`/api/evals/run`, {
    method: 'POST',
  });

export const recompile = () =>
  api<{
    version: string;
    activated: boolean;
    active_version: string;
    devset_agreement: number;
    metrics: any;
    trainset_size: number;
    devset_size: number;
  }>(`/api/evals/recompile`, { method: 'POST' });

export const fetchPromptVersions = () =>
  api<{ items: TheoryPromptVersion[] }>(`/api/evals/prompt-versions`);

export const activateVersion = (versionId: number) =>
  api<{ active: TheoryPromptVersion }>(
    `/api/evals/prompt-versions/${versionId}/activate`,
    { method: 'POST' },
  );

export interface FeedbackPayload {
  feedback_type: string;
  feedback_text: string;
  severity: string;
  human_verdict?: string;
}

export const submitFeedback = (rowKey: string, payload: FeedbackPayload) =>
  api<{ feedback: FeedbackEntry[] }>(
    `/api/theory-questions/${encodeURIComponent(rowKey)}/feedback`,
    { method: 'POST', body: JSON.stringify(payload) },
  );

export const fetchFeedback = (rowKey: string) =>
  api<{ feedback: FeedbackEntry[] }>(
    `/api/theory-questions/${encodeURIComponent(rowKey)}/feedback`,
  );

export const fetchHistory = (rowKey: string) =>
  api<{ items: TagHistoryEntry[] }>(
    `/api/theory-questions/${encodeURIComponent(rowKey)}/history`,
  );

export const fetchImprovementSummary = () =>
  api<ImprovementSummary>(`/api/evals/improvement-summary`);

export interface TagProgressEvent {
  stage: string;
  at_ms: number;
  note?: string;
  [key: string]: unknown;
}

export interface TagProgress {
  row_key: string;
  stage: string;
  trigger?: string;
  prompt_version?: string | null;
  started_at_ms?: number;
  updated_at_ms?: number;
  elapsed_ms?: number;
  events?: TagProgressEvent[];
  kps_count?: number;
  candidates_count?: number;
  accepted_count?: number;
  verdict?: string | null;
  confidence?: number | null;
  error?: string | null;
  result?: {
    verdict?: string;
    overall_confidence?: number;
    review_status?: string;
    required_kps_count?: number;
    citations_count?: number;
    candidate_citations_count?: number;
  } | null;
  completed: boolean;
}

export const fetchTagStatus = (rowKey: string) =>
  api<TagProgress>(`/api/theory-questions/${encodeURIComponent(rowKey)}/tag-status`);

export interface TheoryActiveContext {
  active_prompt_version: {
    id: number;
    version: string;
    fewshot_count: number;
    gold_count_at_compile: number;
    devset_agreement: number | null;
    created_at: string;
  } | null;
  gold_set_total: number;
  feedback_total: number;
  feedback_by_severity: Record<string, number>;
  kp_catalog_size: number;
  auto_approve_threshold: number;
  model: string;
}

export const fetchActiveContext = () =>
  api<TheoryActiveContext>(`/api/evals/active-context`);
