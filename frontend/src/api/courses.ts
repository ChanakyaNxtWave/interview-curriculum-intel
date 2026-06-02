import { api } from './client';
import type {
  CourseGroupedQuestionMembersResponse,
  CourseGroupedQuestionsResponse,
  CoursesResponse,
  KnowledgeGraphResponse,
} from './types';

export const fetchCourses = () => api<CoursesResponse>('/api/courses');

export interface CourseGroupedQuestionsFilters {
  q?: string;
  company_name?: string;
  question_type?: string;
  limit?: number;
  offset?: number;
}

function qs(obj: Record<string, unknown>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === '') continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const fetchCourseGroupedQuestions = (
  courseId: string,
  filters: CourseGroupedQuestionsFilters = {},
) =>
  api<CourseGroupedQuestionsResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/grouped-questions${qs(filters as Record<string, unknown>)}`,
  );

export const fetchCourseGroupedQuestionMembers = (
  courseId: string,
  canonicalId: number,
  limit = 200,
  representativeRowKey?: string,
  similarOnly = false,
) =>
  api<CourseGroupedQuestionMembersResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/grouped-questions/${canonicalId}/members${qs({
      limit,
      representative_row_key: representativeRowKey,
      similar_only: similarOnly || undefined,
    })}`,
  );

export const fetchCourseKnowledgeGraph = (courseId: string) =>
  api<KnowledgeGraphResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph`,
  );
