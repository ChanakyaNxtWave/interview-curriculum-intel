import { api, qs } from './client';
import type {
  InterviewFacets,
  InterviewQuestionsResponse,
  InterviewSyncLog,
  InterviewSyncStatus,
  NormalizeStatus,
  QuestionGroup,
  QuestionGroupMember,
} from './types';

export interface InterviewFilters {
  q?: string;
  company_name?: string;
  role?: string;
  question_type?: string;
  tech_stack?: string;
  product?: string;
  duration?: string;
  date_from?: string;
  date_to?: string;
  group_by?: boolean;
  limit?: number;
  offset?: number;
}

export const fetchInterviewQuestions = (f: InterviewFilters = {}) =>
  api<InterviewQuestionsResponse>(`/api/interview-questions${qs(f)}`);

export const fetchInterviewFacets = () =>
  api<InterviewFacets>('/api/interview-questions/facets');

export const fetchInterviewSyncStatus = () =>
  api<InterviewSyncStatus>('/api/interview-questions/sync-status');

export const triggerInterviewSync = () =>
  api<InterviewSyncLog & { status: string; sync_id: number; fetched_rows: number }>(
    '/api/interview-questions/sync',
    { method: 'POST' },
  );

export const fetchNormalizeStatus = () =>
  api<NormalizeStatus>('/api/interview-questions/normalize-status');

export const triggerNormalize = (limit = 100) =>
  api<{ enqueued: boolean; limit: number; status: NormalizeStatus }>(
    `/api/interview-questions/normalize-now?limit=${limit}`,
    { method: 'POST' },
  );

export const fetchGroupMembers = (groupKey: string) =>
  api<{ group: QuestionGroup; members: QuestionGroupMember[] }>(
    `/api/interview-question-groups/${encodeURIComponent(groupKey)}/members`,
  );

export const deleteInterviewQuestion = (rowKey: string) =>
  api<{
    deleted: boolean;
    row_key: string;
    deleted_row_keys?: string[];
    deleted_count?: number;
    group_key?: string | null;
  }>(
    `/api/interview-questions/${encodeURIComponent(rowKey)}`,
    { method: 'DELETE' },
  );
