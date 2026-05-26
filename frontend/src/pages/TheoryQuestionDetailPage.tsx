import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from 'lucide-react';
import {
  fetchTheoryQuestion,
  submitReview,
  tagTheoryQuestion,
  type ReviewPayload,
} from '../api/theory';
import VerdictBadge from '../components/VerdictBadge';
import ConfidenceBar from '../components/ConfidenceBar';
import ReviewStatusBadge from '../components/ReviewStatusBadge';
import ReasoningPanel from '../components/ReasoningPanel';
import FeedbackPanel from '../components/FeedbackPanel';
import TagHistory from '../components/TagHistory';
import AskedChip from '../components/AskedChip';
import GroupMembersModal from '../components/GroupMembersModal';
import { useDebounce } from '../hooks/useDebounce';
import type {
  ReviewStatus,
  TheoryCitation,
  TheoryRequiredKp,
  TheoryVerdict,
  KnowledgePoint,
} from '../api/types';
import { api } from '../api/client';

interface DraftState {
  kps: TheoryRequiredKp[];
  citations: TheoryCitation[];
  verdict: TheoryVerdict;
  status: ReviewStatus;
  notes: string;
  rationale: string;
}

const VERDICTS: TheoryVerdict[] = ['covered', 'partially_covered', 'not_covered', 'uncertain'];
const STATUSES: ReviewStatus[] = ['pending', 'needs_review', 'approved', 'rejected'];

export default function TheoryQuestionDetailPage() {
  const { rowKey = '', courseId = '' } = useParams();
  const qc = useQueryClient();
  const detailQ = useQuery({
    queryKey: ['theory-detail', rowKey],
    queryFn: () => fetchTheoryQuestion(rowKey),
  });

  const data = detailQ.data;
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setDraft({
      kps: data.human_required_kps?.length ? data.human_required_kps : data.required_kps ?? [],
      citations: data.human_citations?.length ? data.human_citations : data.citations ?? [],
      verdict: (data.human_verdict ?? data.verdict) as TheoryVerdict,
      status: (data.review_status as ReviewStatus) ?? 'pending',
      notes: data.reviewer_notes ?? '',
      rationale: data.rationale ?? '',
    });
  }, [data?.row_key]); // eslint-disable-line react-hooks/exhaustive-deps

  const reTag = useMutation({
    mutationFn: () => tagTheoryQuestion(rowKey),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['theory-detail', rowKey] });
    },
  });

  const save = useMutation({
    mutationFn: (payload: ReviewPayload) => submitReview(rowKey, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['theory-detail', rowKey] });
      qc.invalidateQueries({ queryKey: ['theory-list'] });
    },
  });

  if (detailQ.isLoading || !data || !draft) return <DetailSkeleton />;
  if (detailQ.error) return <div className="text-conf-uncertain">Failed: {String(detailQ.error)}</div>;

  function submit() {
    if (!draft) return;
    save.mutate({
      human_required_kps: draft.kps.map((k) => ({
        source_kp_id: k.source_kp_id,
        confidence: (k.confidence as string) || 'high',
        rationale: k.rationale ?? '',
      })),
      human_citations: draft.citations.map((c) => ({
        content_id: c.content_id,
        kp_id: c.kp_id,
        tag_role: c.tag_role,
      })),
      human_verdict: draft.verdict,
      review_status: draft.status,
      reviewer_notes: draft.notes,
      gold_rationale: draft.rationale,
    });
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
        <Link
          to={`/courses/${courseId}/theory-questions`}
          className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text"
        >
          <ArrowLeft className="w-4 h-4" /> Back to theory list
        </Link>
        <button
          className="btn disabled:opacity-50"
          disabled={reTag.isPending}
          onClick={() => reTag.mutate()}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${reTag.isPending ? 'animate-spin' : ''}`} />
          Re-tag now
        </button>
      </div>

      <div className="card p-5 mb-4">
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <p className="text-text leading-relaxed whitespace-pre-wrap">{data.question_text}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-text-muted">
              {data.interview?.company_name && (
                <span className="chip">{data.interview.company_name}</span>
              )}
              {data.interview?.role && <span className="chip">{data.interview.role}</span>}
              {data.interview?.interview_date && (
                <span className="chip">{data.interview.interview_date}</span>
              )}
              <span className="chip">prompt: {data.prompt_version}</span>
              {data.ai_model && <span className="chip">model: {data.ai_model}</span>}
              {data.group_key && (
                <AskedChip
                  count={data.group_member_count}
                  onClick={() => setOpenGroup(data.group_key as string)}
                />
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0 min-w-[180px]">
            <VerdictBadge verdict={data.verdict} />
            <ConfidenceBar value={data.overall_confidence} />
            <ReviewStatusBadge status={data.review_status as ReviewStatus} />
          </div>
        </div>

        {data.rationale && (
          <div className="mt-4 p-3 rounded-md bg-bg-panel border border-line">
            <div className="text-xs text-text-dim mb-1">AI rationale</div>
            <p className="text-sm text-text whitespace-pre-wrap">{data.rationale}</p>
          </div>
        )}

        {data.review_reasons?.length > 0 && (
          <div className="mt-3 p-3 rounded-md border border-status-needs/40 bg-status-needs/10 text-sm">
            <div className="text-xs font-semibold text-status-needs uppercase tracking-wide mb-1">
              Flagged for review
            </div>
            <ul className="text-text-muted list-disc list-inside space-y-0.5">
              {data.review_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <ReasoningPanel
        kpReasoning={(data as any).kp_identifier_reasoning}
        judgeReasoning={(data as any).judge_reasoning}
        rationale={data.rationale}
        requiredKps={data.required_kps}
        rejectedCandidates={(data as any).rejected_candidates ?? []}
      />

      <FeedbackPanel rowKey={rowKey} activePromptVersion={data.prompt_version} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <KpEditor
          kps={draft.kps}
          onChange={(v) => setDraft({ ...draft, kps: v })}
        />
        <CitationEditor
          citations={draft.citations}
          candidates={data.candidate_citations ?? []}
          onChange={(v) => setDraft({ ...draft, citations: v })}
        />
      </div>

      <div className="card p-4 mt-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-text-dim block mb-1">Verdict</label>
            <select
              className="input w-full"
              value={draft.verdict}
              onChange={(e) => setDraft({ ...draft, verdict: e.target.value as TheoryVerdict })}
            >
              {VERDICTS.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-text-dim block mb-1">Review status</label>
            <select
              className="input w-full"
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value as ReviewStatus })}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3">
          <label className="text-xs text-text-dim block mb-1">Rationale (saved with gold)</label>
          <textarea
            className="input w-full min-h-[80px]"
            value={draft.rationale}
            onChange={(e) => setDraft({ ...draft, rationale: e.target.value })}
            placeholder="Why does this verdict hold?"
          />
        </div>
        <div className="mt-3">
          <label className="text-xs text-text-dim block mb-1">Reviewer notes</label>
          <textarea
            className="input w-full min-h-[60px]"
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            placeholder="Optional internal notes"
          />
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            className="btn-primary disabled:opacity-50"
            disabled={save.isPending}
            onClick={submit}
          >
            <Save className="w-3.5 h-3.5" />
            {save.isPending ? 'Saving…' : 'Save review'}
          </button>
          {save.isSuccess && (
            <span className="inline-flex items-center gap-1 text-sm text-conf-high">
              <CheckCircle2 className="w-4 h-4" /> Saved · gold source:{' '}
              {save.data.eval_source}
            </span>
          )}
          {save.isError && (
            <span className="text-sm text-conf-uncertain">{String(save.error)}</span>
          )}
        </div>
      </div>

      <TagHistory rowKey={rowKey} />

      {reTag.isPending && (
        <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm flex items-center justify-center pointer-events-none">
          <div className="card px-5 py-4 flex items-center gap-3 shadow-2xl">
            <Loader2 className="w-5 h-5 text-brand animate-spin" />
            <div>
              <div className="text-text font-medium">Re-tagging…</div>
              <div className="text-xs text-text-dim">DSPy pipeline running — Sonnet via OpenRouter</div>
            </div>
          </div>
        </div>
      )}

      {openGroup && (
        <GroupMembersModal groupKey={openGroup} onClose={() => setOpenGroup(null)} />
      )}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-5 w-32 bg-bg-panel rounded mb-4" />
      <div className="card p-5 mb-4">
        <div className="h-4 w-full bg-bg-panel rounded mb-2" />
        <div className="h-4 w-3/4 bg-bg-panel rounded mb-3" />
        <div className="flex gap-2">
          <div className="h-5 w-20 bg-bg-panel rounded-full" />
          <div className="h-5 w-24 bg-bg-panel rounded-full" />
          <div className="h-5 w-24 bg-bg-panel rounded-full" />
        </div>
      </div>
      <div className="card p-4 mb-4 h-32 bg-bg-panel/40" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-4 h-40 bg-bg-panel/40" />
        <div className="card p-4 h-40 bg-bg-panel/40" />
      </div>
    </div>
  );
}

function KpEditor({
  kps,
  onChange,
}: {
  kps: TheoryRequiredKp[];
  onChange: (v: TheoryRequiredKp[]) => void;
}) {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 300);
  const search = useQuery({
    queryKey: ['kps-search', debounced],
    queryFn: () =>
      api<{ count: number; knowledge_points: KnowledgePoint[] }>(
        `/api/kps?q=${encodeURIComponent(debounced)}&limit=30`,
      ),
    enabled: debounced.length > 1,
  });
  const taken = new Set(kps.map((k) => k.source_kp_id));

  function add(kp: KnowledgePoint) {
    if (taken.has(kp.source_kp_id)) return;
    onChange([
      ...kps,
      { source_kp_id: kp.source_kp_id, confidence: 'high', rationale: '', label: kp.label },
    ]);
    setQuery('');
  }
  function remove(id: string) {
    onChange(kps.filter((k) => k.source_kp_id !== id));
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-text">Required KPs</h2>
        <span className="text-xs text-text-dim">{kps.length}</span>
      </div>
      <div className="relative mb-3">
        <input
          className="input w-full"
          placeholder="Search KP label or id to add…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {debounced.length > 1 && search.data?.knowledge_points && (
          <div className="absolute z-10 mt-1 left-0 right-0 max-h-64 overflow-auto card border-line shadow-xl">
            {search.data.knowledge_points
              .filter((kp) => !taken.has(kp.source_kp_id))
              .slice(0, 15)
              .map((kp) => (
                <button
                  key={kp.source_kp_id}
                  className="block w-full text-left px-3 py-2 hover:bg-bg-hover border-b border-line"
                  onClick={() => add(kp)}
                >
                  <span className="font-mono text-xs text-text-dim mr-2">{kp.source_kp_id}</span>
                  <span className="text-sm text-text">{kp.label}</span>
                </button>
              ))}
          </div>
        )}
      </div>
      {kps.length === 0 ? (
        <div className="text-sm text-text-muted">No KPs assigned.</div>
      ) : (
        <div className="space-y-2">
          {kps.map((k) => (
            <div
              key={k.source_kp_id}
              className="p-3 rounded-md border border-line bg-bg-panel flex items-start gap-2"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-brand">{k.source_kp_id}</span>
                  {k.label && <span className="text-sm text-text">{k.label}</span>}
                </div>
                {k.rationale && (
                  <p className="text-xs text-text-muted mt-1 line-clamp-2">{k.rationale}</p>
                )}
              </div>
              <button
                className="text-text-dim hover:text-conf-uncertain"
                onClick={() => remove(k.source_kp_id)}
                aria-label="Remove KP"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CitationEditor({
  citations,
  candidates,
  onChange,
}: {
  citations: TheoryCitation[];
  candidates: TheoryCitation[];
  onChange: (v: TheoryCitation[]) => void;
}) {
  const taken = new Set(citations.map((c) => c.content_id));
  const remaining = candidates.filter((c) => !taken.has(c.content_id));

  function add(c: TheoryCitation) {
    onChange([...citations, c]);
  }
  function remove(id: string) {
    onChange(citations.filter((c) => c.content_id !== id));
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-text">Citations</h2>
        <span className="text-xs text-text-dim">{citations.length}</span>
      </div>
      {citations.length === 0 ? (
        <div className="text-sm text-text-muted mb-2">No citations.</div>
      ) : (
        <div className="space-y-2 mb-3">
          {citations.map((c) => (
            <div
              key={c.content_id}
              className="p-3 rounded-md border border-line bg-bg-panel flex items-start gap-2"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <Link
                    to={`/content/${encodeURIComponent(c.content_id)}`}
                    className="text-sm font-medium text-brand hover:underline truncate inline-flex items-center gap-1"
                  >
                    {c.title ?? c.content_id} <ExternalLink className="w-3 h-3" />
                  </Link>
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-text-muted">
                  {c.kp_id && <span className="chip">{c.kp_id}</span>}
                  {c.tag_role && <span className="chip">{c.tag_role}</span>}
                  {c.topic_name && <span className="chip">{c.topic_name}</span>}
                </div>
                {c.snippet && (
                  <p className="text-xs text-text-dim mt-1 line-clamp-2 font-mono">{c.snippet}</p>
                )}
              </div>
              <button
                className="text-text-dim hover:text-conf-uncertain"
                onClick={() => remove(c.content_id)}
                aria-label="Remove citation"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {remaining.length > 0 && (
        <div>
          <div className="text-xs text-text-dim mb-1.5">Add from candidates:</div>
          <div className="space-y-1.5">
            {remaining.slice(0, 8).map((c) => (
              <button
                key={c.content_id}
                className="w-full text-left p-2 rounded-md border border-line bg-bg-panel hover:bg-bg-hover flex items-start gap-2"
                onClick={() => add(c)}
              >
                <Plus className="w-3.5 h-3.5 mt-0.5 text-brand shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-text truncate">{c.title}</div>
                  <div className="text-xs text-text-dim">
                    {c.kp_id} · {c.tag_role}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
