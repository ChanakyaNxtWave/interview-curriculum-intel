// CODING-namespace API client. Mirrors the coding-relevant calls in theory.ts
// against the dedicated /api/coding-questions/* routes. CODING tags live in
// physically separate tables (coding_question_tags / coding_tag_history) but
// share the same row/tag shape, so we reuse the theory types.
import { api, qs } from './client';
import type {
  FeedbackEntry,
  TagHistoryEntry,
  TheoryListResponse,
  TheoryTag,
} from './types';
import type {
  ReviewPayload,
  FeedbackPayload,
  TheoryListFilters,
  TagStartResponse,
} from './theory';

export const fetchCodingQuestions = (f: TheoryListFilters = {}) =>
  api<TheoryListResponse>(`/api/coding-questions${qs(f)}`);

export const fetchCodingQuestion = (rowKey: string) =>
  api<TheoryTag>(`/api/coding-questions/${encodeURIComponent(rowKey)}`);

export const tagCodingQuestion = (rowKey: string) =>
  api<TagStartResponse>(`/api/coding-questions/${encodeURIComponent(rowKey)}/tag`, {
    method: 'POST',
  });

export const fetchCodingTagStatus = (rowKey: string) =>
  api<import('./theory').TagProgress>(
    `/api/coding-questions/${encodeURIComponent(rowKey)}/tag-status`,
  );

export const tagCodingPending = (limit = 50) =>
  api<{ enqueued: number }>(`/api/coding-questions/tag-pending`, {
    method: 'POST',
    body: JSON.stringify({ limit }),
  });

export const tagCodingBatch = (rowKeys: string[]) =>
  api<{ enqueued: number }>(`/api/coding-questions/tag-batch`, {
    method: 'POST',
    body: JSON.stringify({ row_keys: rowKeys }),
  });

export const fetchCodingPendingCount = () =>
  api<{
    pending: number;
    by_type?: { THEORY?: number; CODING?: number };
    total_representatives: number;
  }>(`/api/coding-questions/pending-count`);

export const submitCodingReview = (rowKey: string, payload: ReviewPayload) =>
  api<{ tag: TheoryTag; eval_source: string }>(
    `/api/coding-questions/${encodeURIComponent(rowKey)}/review`,
    { method: 'PUT', body: JSON.stringify(payload) },
  );

export const submitCodingFeedback = (rowKey: string, payload: FeedbackPayload) =>
  api<{ feedback: FeedbackEntry[] }>(
    `/api/coding-questions/${encodeURIComponent(rowKey)}/feedback`,
    { method: 'POST', body: JSON.stringify(payload) },
  );

export const fetchCodingFeedback = (rowKey: string) =>
  api<{ feedback: FeedbackEntry[] }>(
    `/api/coding-questions/${encodeURIComponent(rowKey)}/feedback`,
  );

export const fetchCodingHistory = (rowKey: string) =>
  api<{ items: TagHistoryEntry[] }>(
    `/api/coding-questions/${encodeURIComponent(rowKey)}/history`,
  );
