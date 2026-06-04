import { api } from './client';
import type {
  KgExpansionRun,
  KgExpansionRunDetailResponse,
  KgExpansionViewResponse,
  UncoveredQuestion,
} from './types';

function qs(obj: Record<string, unknown>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === '') continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const fetchKgExpansionView = (courseId: string, runId?: number) =>
  api<KgExpansionViewResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion${qs({
      run_id: runId,
    })}`,
  );

export const fetchKgExpansionRuns = (courseId: string, limit = 20) =>
  api<{ course_id: string; runs: KgExpansionRun[] }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion/runs${qs({ limit })}`,
  );

export const fetchKgExpansionRunDetail = (courseId: string, runId: number) =>
  api<KgExpansionRunDetailResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion/runs/${runId}`,
  );

export const fetchUncoveredQuestions = (courseId: string, limit = 500) =>
  api<{ course_id: string; total: number; items: UncoveredQuestion[] }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/uncovered-questions${qs({ limit })}`,
  );

export const startKgExpansionRun = (
  courseId: string,
  body: { question_limit?: number; model?: string } = {},
) =>
  api<{ enqueued: boolean; run: KgExpansionRun; question_count: number }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion/runs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );

export type ExpansionFeedbackType =
  | 'over_granular'
  | 'missing_prereq'
  | 'prereq_dump'
  | 'wrong_catalog_match'
  | 'label_quality'
  | 'approved'
  | 'general';

export type ExpansionHumanVerdict = 'approved' | 'rejected' | 'needs_revision';

export interface ExpansionFeedbackPayload {
  row_key: string;
  proposed_kp_label?: string;
  feedback_type: ExpansionFeedbackType;
  feedback_text?: string;
  severity?: 'low' | 'medium' | 'high';
  human_verdict: ExpansionHumanVerdict;
}

export const submitExpansionFeedback = (
  courseId: string,
  runId: number,
  payload: ExpansionFeedbackPayload,
) =>
  api<{ feedback_id: number; feedback: unknown[] }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion/runs/${runId}/feedback`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );

export const fetchExpansionFeedback = (courseId: string, runId: number) =>
  api<{ run_id: number; feedback: unknown[]; rejection_patterns: string }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion/runs/${runId}/feedback`,
  );

export const fetchExpansionFeedbackSummary = (courseId: string) =>
  api<{
    course_id: string;
    total_feedback: number;
    total_rejected: number;
    rejection_by_type: Record<string, number>;
    rejection_rate: number;
  }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion/feedback-summary`,
  );

export const purgeKgExpansionData = (courseId: string) =>
  api<{ course_id: string; purged: Record<string, number> }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/expansion/purge`,
    { method: 'POST' },
  );
