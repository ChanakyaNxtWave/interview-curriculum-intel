import { api } from './client';
import type {
  NodeTaggerApprovalStatus,
  NodeTaggerCanonicalNodesResponse,
  NodeTaggerRun,
  NodeTaggerRunDetailResponse,
  NodeTaggerViewResponse,
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

export const fetchNodeTaggerView = (courseId: string, runId?: number) =>
  api<NodeTaggerViewResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/expansion${qs({
      run_id: runId,
    })}`,
  );

export const fetchNodeTaggerRuns = (courseId: string, limit = 20) =>
  api<{ course_id: string; runs: NodeTaggerRun[] }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/runs${qs({
      limit,
    })}`,
  );

export const fetchNodeTaggerRunDetail = (courseId: string, runId: number) =>
  api<NodeTaggerRunDetailResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/runs/${runId}`,
  );

export const fetchNodeTaggerUncoveredQuestions = (courseId: string, limit = 500) =>
  api<{ course_id: string; total: number; items: UncoveredQuestion[] }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/uncovered-questions${qs(
      { limit },
    )}`,
  );

export const startNodeTaggerRun = (
  courseId: string,
  body: { question_limit?: number; question_type?: string | null; model?: string } = {},
) =>
  api<{ enqueued: boolean; run: NodeTaggerRun; question_count: number }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/runs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );

export const purgeNodeTaggerData = (courseId: string) =>
  api<{ course_id: string; purged: Record<string, number> }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/purge`,
    { method: 'POST' },
  );

export const setNodeApproval = (
  courseId: string,
  runId: number,
  knowledgeNodeId: string,
  approvalStatus: NodeTaggerApprovalStatus,
) =>
  api<{ node: import('./types').NodeTaggerProposedNode; canonical_nodes_count: number }>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/runs/${runId}/nodes/${encodeURIComponent(knowledgeNodeId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_status: approvalStatus }),
    },
  );

export const fetchCanonicalNodes = (courseId: string) =>
  api<NodeTaggerCanonicalNodesResponse>(
    `/api/courses/${encodeURIComponent(courseId)}/knowledge-graph/node-tagger/canonical-nodes`,
  );
