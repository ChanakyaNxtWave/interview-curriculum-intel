import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Check, GitBranch, Play, RefreshCw, Sparkles, X } from 'lucide-react';
import {
  fetchExpansionFeedback,
  fetchKgExpansionRuns,
  fetchKgExpansionView,
  startKgExpansionRun,
  submitExpansionFeedback,
} from '../../api/kgExpansion';
import type { ExpansionFeedbackType, ExpansionFeedbackPayload } from '../../api/kgExpansion';
import KnowledgeGraphCanvas from './KnowledgeGraphCanvas';
import type { KgExpansionRun, KgProposedKp, UncoveredQuestion } from '../../api/types';

interface GapExpansionPanelProps {
  courseId: string;
  baselineGraph: import('../../api/types').KnowledgeGraphResponse;
}

export default function GapExpansionPanel({ courseId, baselineGraph }: GapExpansionPanelProps) {
  const qc = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(undefined);
  const [questionLimit, setQuestionLimit] = useState(25);
  const [sideTab, setSideTab] = useState<'proposed' | 'unmatched' | 'matched' | 'uncovered'>(
    'proposed',
  );
  const [graphMode, setGraphMode] = useState<'expanded' | 'baseline'>('expanded');

  const runsQ = useQuery({
    queryKey: ['kg-expansion-runs', courseId],
    queryFn: () => fetchKgExpansionRuns(courseId),
    refetchInterval: (q) => {
      const runs = q.state.data?.runs ?? [];
      if (runs.some((r) => r.status === 'running' || r.status === 'pending')) return 3000;
      return false;
    },
  });

  const viewQ = useQuery({
    queryKey: ['kg-expansion-view', courseId, selectedRunId],
    queryFn: () => fetchKgExpansionView(courseId, selectedRunId),
    refetchInterval: (q) => {
      const status = q.state.data?.run?.status;
      if (status === 'running' || status === 'pending') return 3000;
      return false;
    },
  });

  const activeRun = viewQ.data?.run;
  const expansion = viewQ.data?.expanded?.expansion;
  const expandedGraph = viewQ.data?.expanded;
  const uncovered = viewQ.data?.uncovered_questions;
  const isRunning = activeRun?.status === 'running' || activeRun?.status === 'pending';
  const hasCompletedRun = activeRun?.status === 'completed' && expandedGraph != null;

  const displayGraph = useMemo(() => {
    if (graphMode === 'baseline' || !hasCompletedRun) return baselineGraph;
    return expandedGraph ?? baselineGraph;
  }, [graphMode, hasCompletedRun, baselineGraph, expandedGraph]);

  useEffect(() => {
    if (selectedRunId != null) return;
    const latest = runsQ.data?.runs.find((r) => r.status === 'completed');
    if (latest) setSelectedRunId(latest.id);
  }, [runsQ.data, selectedRunId]);

  const startRun = useMutation({
    mutationFn: () => startKgExpansionRun(courseId, { question_limit: questionLimit }),
    onSuccess: (data) => {
      setSelectedRunId(data.run.id);
      qc.invalidateQueries({ queryKey: ['kg-expansion-runs', courseId] });
      qc.invalidateQueries({ queryKey: ['kg-expansion-view', courseId] });
    },
  });

  return (
    <div className="space-y-4">
      <div
        className="flex items-center gap-2 rounded-md border border-status-needs/40 bg-status-needs/10 px-3 py-2 text-sm text-status-needs"
        role="status"
      >
        <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
        <span>
          <span className="font-medium">In testing</span>
          <span className="text-status-needs/90">
            {' '}
            — gap expansion proposes new KPs from uncovered questions; review before merging.
          </span>
        </span>
      </div>
      <div className="card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3 justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium">
              <Sparkles className="w-4 h-4 text-brand" />
              Gap expansion (IPA → LTA → KP proposal)
            </div>
            <p className="text-xs text-text-muted mt-1 max-w-2xl">
              Processes <code className="text-text">not_covered</code> questions, maps skills to
              the catalog, links existing KPs via <code className="text-text">prerequisite_skill_ids</code>,
              and creates consolidated proposed KPs when needed.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-text-muted flex items-center gap-1">
              Limit
              <input
                type="number"
                min={1}
                max={200}
                value={questionLimit}
                onChange={(e) => setQuestionLimit(Number(e.target.value) || 25)}
                className="input w-16 text-sm py-1"
                disabled={isRunning || startRun.isPending}
              />
            </label>
            <select
              className="input text-sm max-w-[200px]"
              value={selectedRunId ?? ''}
              onChange={(e) =>
                setSelectedRunId(e.target.value ? Number(e.target.value) : undefined)
              }
            >
              <option value="">Latest completed run</option>
              {(runsQ.data?.runs ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} · {r.status} · {r.processed_count}/{r.total_questions}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-primary text-sm inline-flex items-center gap-1.5"
              disabled={isRunning || startRun.isPending}
              onClick={() => startRun.mutate()}
            >
              {isRunning || startRun.isPending ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              Run expansion
            </button>
            <button
              type="button"
              className="btn text-sm"
              onClick={() => {
                qc.invalidateQueries({ queryKey: ['kg-expansion-view', courseId] });
                qc.invalidateQueries({ queryKey: ['kg-expansion-runs', courseId] });
              }}
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {activeRun && <RunStatusBanner run={activeRun} />}
        {startRun.isError && (
          <div className="text-sm text-conf-uncertain">{String(startRun.error)}</div>
        )}
        {uncovered && (
          <div className="text-xs text-text-muted">
            {uncovered.total} uncovered question(s) (theory + coding, verdict not_covered)
          </div>
        )}
      </div>

      <div className="flex flex-col xl:flex-row gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-sm text-text-muted">Knowledge graph</span>
            {hasCompletedRun && (
              <nav className="inline-flex rounded border border-line overflow-hidden text-xs">
                <button
                  type="button"
                  className={graphMode === 'expanded' ? 'chip-on px-2 py-1' : 'chip px-2 py-1'}
                  onClick={() => setGraphMode('expanded')}
                >
                  With proposed (+{expansion?.diff?.added_node_count ?? 0})
                </button>
                <button
                  type="button"
                  className={graphMode === 'baseline' ? 'chip-on px-2 py-1' : 'chip px-2 py-1'}
                  onClick={() => setGraphMode('baseline')}
                >
                  Baseline only
                </button>
              </nav>
            )}
          </div>
          <KnowledgeGraphCanvas
            graph={displayGraph}
            visibleLevels={null}
            searchQuery=""
            selectedId={null}
            onSelectNode={() => {}}
          />
          <p className="text-xs text-text-dim mt-2 flex items-center gap-1">
            <GitBranch className="w-3.5 h-3.5" />
            Amber nodes are proposed KPs from this run (touch count = uncovered questions mapped).
          </p>
        </div>

        <aside className="w-full xl:w-96 shrink-0 space-y-3">
          <nav className="card p-1 inline-flex flex-wrap gap-1 w-full">
            {(
              [
                ['proposed', 'Proposed KPs'],
                ['unmatched', 'Unmatched'],
                ['matched', 'Catalog'],
                ['uncovered', 'Questions'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={
                  sideTab === id ? 'chip-on flex-1 text-center text-xs' : 'chip flex-1 text-center text-xs'
                }
                onClick={() => setSideTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          {sideTab === 'proposed' && (
            <ProposedKpsPanel
              items={expansion?.proposed_kps ?? []}
              diff={expansion?.diff}
              hasRun={hasCompletedRun}
              courseId={courseId}
              runId={activeRun?.id}
            />
          )}
          {sideTab === 'unmatched' && (
            <UnmatchedSkillsPanel
              items={expansion?.unmatched_skills ?? []}
              hasRun={hasCompletedRun}
            />
          )}
          {sideTab === 'matched' && (
            <MatchedKpsPanel items={expansion?.matched_catalog_kps ?? []} hasRun={hasCompletedRun} />
          )}
          {sideTab === 'uncovered' && (
            <UncoveredPanel items={uncovered?.items ?? []} total={uncovered?.total ?? 0} />
          )}
        </aside>
      </div>
    </div>
  );
}

function RunStatusBanner({ run }: { run: KgExpansionRun }) {
  const stats = run.stats as Record<string, number | string>;
  return (
    <div
      className={`rounded-md border px-3 py-2 text-sm ${
        run.status === 'failed'
          ? 'border-conf-uncertain/40 bg-conf-uncertain/10'
          : run.status === 'completed'
            ? 'border-conf-covered/40 bg-conf-covered/10'
            : 'border-brand/40 bg-brand/10'
      }`}
    >
      <div className="font-medium">
        Run #{run.id} · {run.status}
        {(run.status === 'running' || run.status === 'pending') &&
          ` (${run.processed_count}/${run.total_questions})`}
      </div>
      {run.status === 'completed' && (
        <div className="text-xs text-text-muted mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          <span>new KPs: {stats.new_kps ?? 0}</span>
          <span>catalog matches: {stats.matched_catalog ?? 0}</span>
          <span>unmatched skills: {stats.unmatched_skills ?? 0}</span>
          {stats.prompt_version != null && (
            <span className="text-text-dim">prompt {String(stats.prompt_version)}</span>
          )}
        </div>
      )}
      {run.error_message && (
        <div className="text-xs text-conf-uncertain mt-1">{run.error_message}</div>
      )}
    </div>
  );
}

const REJECTION_REASONS: { value: ExpansionFeedbackType; label: string }[] = [
  { value: 'over_granular', label: 'Too granular' },
  { value: 'missing_prereq', label: 'Missing prereqs' },
  { value: 'prereq_dump', label: 'Prereq dump' },
  { value: 'wrong_catalog_match', label: 'Wrong catalog match' },
  { value: 'label_quality', label: 'Label quality' },
  { value: 'general', label: 'Other' },
];

function ProposedKpsPanel({
  items,
  diff,
  hasRun,
  courseId,
  runId,
}: {
  items: KgProposedKp[];
  diff?: { added_node_count?: number; baseline_node_count?: number; expanded_node_count?: number };
  hasRun: boolean;
  courseId: string;
  runId: number | undefined;
}) {
  const qc = useQueryClient();
  const [openRejectId, setOpenRejectId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState<ExpansionFeedbackType>('over_granular');
  const [rejectNotes, setRejectNotes] = useState('');

  const feedbackQ = useQuery({
    queryKey: ['kg-expansion-feedback', courseId, runId],
    queryFn: () => (runId ? fetchExpansionFeedback(courseId, runId) : null),
    enabled: !!runId && hasRun,
  });

  const feedbackByLabel = useMemo(() => {
    const map: Record<string, string> = {};
    for (const fb of (feedbackQ.data?.feedback ?? []) as Array<{ proposed_kp_label?: string; human_verdict?: string }>) {
      if (fb.proposed_kp_label) map[fb.proposed_kp_label] = fb.human_verdict ?? '';
    }
    return map;
  }, [feedbackQ.data]);

  const submitFb = useMutation({
    mutationFn: (payload: ExpansionFeedbackPayload) =>
      runId ? submitExpansionFeedback(courseId, runId, payload) : Promise.reject('no run'),
    onSuccess: () => {
      setOpenRejectId(null);
      setRejectNotes('');
      qc.invalidateQueries({ queryKey: ['kg-expansion-feedback', courseId, runId] });
    },
  });

  if (!hasRun) {
    return (
      <div className="card p-4 text-sm text-text-muted">
        Run gap expansion to propose new KPs for uncovered questions.
      </div>
    );
  }

  return (
    <div className="card p-4 text-sm max-h-[50vh] overflow-y-auto">
      {diff && (
        <p className="text-xs text-text-muted mb-3">
          {diff.baseline_node_count} → {diff.expanded_node_count} nodes (+{diff.added_node_count}{' '}
          proposed)
        </p>
      )}
      {items.length === 0 ? (
        <p className="text-text-muted text-xs">No new KPs proposed — catalog covered all gaps.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((row) => {
            const verdict = feedbackByLabel[row.label];
            const isRejecting = openRejectId === row.proposed_kp_id;
            return (
              <li
                key={row.proposed_kp_id}
                className={`p-2 rounded border ${
                  verdict === 'approved'
                    ? 'border-conf-covered/40 bg-conf-covered/5'
                    : verdict === 'rejected'
                      ? 'border-conf-uncertain/40 bg-conf-uncertain/5 opacity-60'
                      : 'border-status-needs/30 bg-status-needs/5'
                }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <div className="font-medium capitalize text-xs flex-1">{row.label}</div>
                  {verdict ? (
                    <span
                      className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                        verdict === 'approved'
                          ? 'bg-conf-covered/20 text-conf-covered'
                          : 'bg-conf-uncertain/20 text-conf-uncertain'
                      }`}
                    >
                      {verdict}
                    </span>
                  ) : (
                    runId && (
                      <div className="flex gap-1 shrink-0">
                        <button
                          type="button"
                          title="Approve"
                          className="p-0.5 rounded text-conf-covered hover:bg-conf-covered/10"
                          onClick={() =>
                            submitFb.mutate({
                              row_key: row.proposed_kp_id,
                              proposed_kp_label: row.label,
                              feedback_type: 'approved',
                              human_verdict: 'approved',
                            })
                          }
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          title="Reject"
                          className="p-0.5 rounded text-conf-uncertain hover:bg-conf-uncertain/10"
                          onClick={() => {
                            setOpenRejectId(row.proposed_kp_id);
                            setRejectReason('over_granular');
                          }}
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )
                  )}
                </div>
                {row.description && (
                  <p className="text-[10px] text-text-muted mt-1 line-clamp-2">{row.description}</p>
                )}
                <div className="text-[10px] text-text-dim mt-1 font-mono">
                  {row.proposed_kp_id} · {row.touch_count} question(s)
                </div>
                {isRejecting && (
                  <div className="mt-2 space-y-1.5 border-t border-line pt-2">
                    <select
                      className="input text-[11px] w-full py-1"
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value as ExpansionFeedbackType)}
                    >
                      {REJECTION_REASONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      className="input text-[11px] w-full py-1"
                      placeholder="Notes (optional)"
                      value={rejectNotes}
                      onChange={(e) => setRejectNotes(e.target.value)}
                    />
                    <div className="flex gap-1">
                      <button
                        type="button"
                        className="btn btn-primary text-[11px] py-0.5 px-2"
                        disabled={submitFb.isPending}
                        onClick={() =>
                          submitFb.mutate({
                            row_key: row.proposed_kp_id,
                            proposed_kp_label: row.label,
                            feedback_type: rejectReason,
                            feedback_text: rejectNotes || undefined,
                            human_verdict: 'rejected',
                          })
                        }
                      >
                        Confirm reject
                      </button>
                      <button
                        type="button"
                        className="btn text-[11px] py-0.5 px-2"
                        onClick={() => setOpenRejectId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                    {submitFb.isError && (
                      <p className="text-[10px] text-conf-uncertain">{String(submitFb.error)}</p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function UnmatchedSkillsPanel({
  items,
  hasRun,
}: {
  items: { normalized_statement?: string; touch_count?: number; best_similarity?: number }[];
  hasRun: boolean;
}) {
  if (!hasRun) {
    return (
      <div className="card p-4 text-sm text-text-muted">
        Run expansion to see skills that still need catalog or proposal coverage.
      </div>
    );
  }
  return (
    <div className="card p-4 text-sm max-h-[50vh] overflow-y-auto">
      <p className="text-xs text-text-muted mb-3">
        Normalized skills with no catalog or proposed KP match.
      </p>
      {items.length === 0 ? (
        <p className="text-text-muted text-xs">No unmatched skills in this run.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((row) => (
            <li
              key={row.normalized_statement}
              className="p-2 rounded border border-line bg-bg-panel"
            >
              <div className="font-medium capitalize text-xs">{row.normalized_statement}</div>
              <div className="text-[10px] text-text-dim mt-1">
                {row.touch_count} question(s) · best similarity{' '}
                {((row.best_similarity ?? 0) * 100).toFixed(0)}%
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MatchedKpsPanel({
  items,
  hasRun,
}: {
  items: {
    source_kp_id?: string;
    label?: string;
    touch_count?: number;
  }[];
  hasRun: boolean;
}) {
  if (!hasRun) {
    return (
      <div className="card p-4 text-sm text-text-muted">
        Run expansion to see existing catalog KPs linked to uncovered questions.
      </div>
    );
  }
  return (
    <div className="card p-4 text-sm max-h-[50vh] overflow-y-auto">
      {items.length === 0 ? (
        <p className="text-text-muted text-xs">No catalog KPs matched in this run.</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-text-dim border-b border-line">
              <th className="pb-1 pr-2">KP</th>
              <th className="pb-1 text-right">Questions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.source_kp_id} className="border-b border-line/50">
                <td className="py-1.5 pr-2 capitalize">{row.label}</td>
                <td className="py-1.5 text-right font-mono">{row.touch_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function UncoveredPanel({
  items,
  total,
}: {
  items: UncoveredQuestion[];
  total: number;
}) {
  return (
    <div className="card p-4 text-sm max-h-[50vh] overflow-y-auto">
      <div className="text-xs text-text-muted mb-2">
        {total} question(s) with verdict <code className="text-text">not_covered</code>
      </div>
      <ul className="space-y-2">
        {items.slice(0, 50).map((q) => (
          <li key={q.row_key} className="p-2 rounded border border-line bg-bg-panel">
            <div className="flex gap-1 mb-1">
              <span className="chip text-[10px]">{q.question_type}</span>
            </div>
            <p className="text-xs text-text line-clamp-3">{q.question_text}</p>
          </li>
        ))}
      </ul>
      {total > 50 && <p className="text-xs text-text-dim mt-2">Showing 50 of {total}</p>}
    </div>
  );
}
