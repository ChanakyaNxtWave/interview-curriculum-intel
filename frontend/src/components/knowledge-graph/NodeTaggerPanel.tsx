import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Play,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react';
import {
  fetchCanonicalNodes,
  fetchNodeTaggerRunDetail,
  fetchNodeTaggerRuns,
  fetchNodeTaggerView,
  setNodeApproval,
  startNodeTaggerRun,
} from '../../api/nodeTagger';
import KnowledgeGraphCanvas from './KnowledgeGraphCanvas';
import type {
  KnowledgeGraphResponse,
  NodeTaggerCanonicalNode,
  NodeTaggerProposedNode,
  NodeTaggerQuestionResult,
  NodeTaggerRun,
} from '../../api/types';

interface NodeTaggerPanelProps {
  courseId: string;
  baselineGraph: KnowledgeGraphResponse;
}

export default function NodeTaggerPanel({ courseId, baselineGraph }: NodeTaggerPanelProps) {
  const qc = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(undefined);
  const [questionLimit, setQuestionLimit] = useState(25);
  const [sideTab, setSideTab] = useState<'proposed' | 'questions' | 'approved'>('proposed');
  const [graphMode, setGraphMode] = useState<'expanded' | 'baseline'>('expanded');

  const runsQ = useQuery({
    queryKey: ['node-tagger-runs', courseId],
    queryFn: () => fetchNodeTaggerRuns(courseId),
    refetchInterval: (q) => {
      const runs = q.state.data?.runs ?? [];
      if (runs.some((r) => r.status === 'running' || r.status === 'pending')) return 3000;
      return false;
    },
  });

  const viewQ = useQuery({
    queryKey: ['node-tagger-view', courseId, selectedRunId],
    queryFn: () => fetchNodeTaggerView(courseId, selectedRunId),
    refetchInterval: (q) => {
      const status = q.state.data?.run?.status;
      if (status === 'running' || status === 'pending') return 3000;
      return false;
    },
  });

  // Run detail (enriched questions + proposed nodes with question_previews)
  const detailQ = useQuery({
    queryKey: ['node-tagger-detail', courseId, selectedRunId],
    queryFn: () =>
      selectedRunId != null ? fetchNodeTaggerRunDetail(courseId, selectedRunId) : null,
    enabled: selectedRunId != null,
    refetchInterval: (q) => {
      const status = (q.state.data as import('../../api/types').NodeTaggerRunDetailResponse | null)
        ?.run?.status;
      if (status === 'running' || status === 'pending') return 3000;
      return false;
    },
  });

  const canonicalQ = useQuery({
    queryKey: ['node-tagger-canonical', courseId],
    queryFn: () => fetchCanonicalNodes(courseId),
  });

  const activeRun = viewQ.data?.run;
  const expandedGraph = viewQ.data?.expanded;
  const expansion = expandedGraph?.expansion as
    | {
        run_id: number;
        proposed_nodes?: NodeTaggerProposedNode[];
        diff?: { added_node_count?: number; baseline_node_count?: number; expanded_node_count?: number };
      }
    | undefined;
  const uncovered = viewQ.data?.uncovered_questions;
  const isRunning = activeRun?.status === 'running' || activeRun?.status === 'pending';
  const hasCompletedRun = activeRun?.status === 'completed' && expandedGraph != null;

  // Prefer detail-query proposed nodes (they have question_previews + approval_status)
  const proposedNodes: NodeTaggerProposedNode[] =
    detailQ.data?.proposed_nodes ?? expansion?.proposed_nodes ?? [];
  const questions: NodeTaggerQuestionResult[] = detailQ.data?.questions ?? [];
  const canonicalNodes: NodeTaggerCanonicalNode[] = canonicalQ.data?.nodes ?? [];

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
    mutationFn: () => startNodeTaggerRun(courseId, { question_limit: questionLimit, skip_processed: true }),
    onSuccess: (data) => {
      setSelectedRunId(data.run.id);
      qc.invalidateQueries({ queryKey: ['node-tagger-runs', courseId] });
      qc.invalidateQueries({ queryKey: ['node-tagger-view', courseId] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: ({
      runId,
      nodeId,
      status,
    }: {
      runId: number;
      nodeId: string;
      status: 'approved' | 'rejected';
    }) => setNodeApproval(courseId, runId, nodeId, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['node-tagger-detail', courseId, selectedRunId] });
      qc.invalidateQueries({ queryKey: ['node-tagger-canonical', courseId] });
      qc.invalidateQueries({ queryKey: ['node-tagger-view', courseId, selectedRunId] });
    },
  });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3 justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium">
              <Sparkles className="w-4 h-4 text-brand" />
              Uncovered KP tagger — 2-phase coverage analysis
            </div>
            <p className="text-xs text-text-muted mt-1 max-w-2xl">
              Processes <code className="text-text">not_covered</code> questions. Each run skips
              already-tagged questions. Proposed KPs show the{' '}
              <span className="font-medium text-text">number of unique companies</span> asking
              questions that need that concept. Approve a KP to persist it as canonical — future
              runs will treat it as an existing node and won't re-propose it.
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
              Run tagger
            </button>
            <button
              type="button"
              className="btn text-sm"
              onClick={() => {
                qc.invalidateQueries({ queryKey: ['node-tagger-view', courseId] });
                qc.invalidateQueries({ queryKey: ['node-tagger-runs', courseId] });
                qc.invalidateQueries({ queryKey: ['node-tagger-detail', courseId, selectedRunId] });
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
          <div className="text-xs text-text-muted flex gap-3">
            <span>{uncovered.total} not_covered questions total</span>
            {(uncovered as { total_processed?: number }).total_processed != null && (
              <span className="text-brand">
                {(uncovered as { total_processed?: number }).total_processed} already tagged
              </span>
            )}
            {canonicalNodes.length > 0 && (
              <span className="text-conf-covered">{canonicalNodes.length} canonical node(s) approved</span>
            )}
          </div>
        )}
      </div>

      {/* Graph + sidebar */}
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
            Amber nodes = proposed KPs. Badge = unique companies asking questions that need this KP.
          </p>
        </div>

        {/* Sidebar */}
        <aside className="w-full xl:w-[420px] shrink-0 space-y-3">
          <nav className="card p-1 inline-flex flex-wrap gap-1 w-full">
            {(
              [
                ['proposed', `Proposed KPs${proposedNodes.length ? ` (${proposedNodes.length})` : ''}`],
                ['questions', `Questions${questions.length ? ` (${questions.length})` : ''}`],
                ['approved', `Approved${canonicalNodes.length ? ` (${canonicalNodes.length})` : ''}`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={
                  sideTab === id
                    ? 'chip-on flex-1 text-center text-xs'
                    : 'chip flex-1 text-center text-xs'
                }
                onClick={() => setSideTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          {sideTab === 'proposed' && (
            <ProposedNodesPanel
              items={proposedNodes}
              diff={expansion?.diff}
              hasRun={hasCompletedRun}
              runId={selectedRunId}
              onApprove={(nodeId, status) =>
                selectedRunId != null &&
                approveMutation.mutate({ runId: selectedRunId, nodeId, status })
              }
              isApproving={approveMutation.isPending}
            />
          )}
          {sideTab === 'questions' && (
            <QuestionsPanel items={questions} hasRun={hasCompletedRun} />
          )}
          {sideTab === 'approved' && <ApprovedPanel nodes={canonicalNodes} />}
        </aside>
      </div>
    </div>
  );
}

// ── Run status banner ────────────────────────────────────────────────────────

function RunStatusBanner({ run }: { run: NodeTaggerRun }) {
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
          <span>processed: {stats.processed ?? 0}</span>
          <span>unique proposed: {stats.unique_proposed_nodes ?? 0}</span>
          <span>full coverage: {stats.full_coverage ?? 0}</span>
          {(stats.errors ?? 0) > 0 && (
            <span className="text-conf-uncertain">errors: {stats.errors}</span>
          )}
        </div>
      )}
      {run.error_message && (
        <div className="text-xs text-conf-uncertain mt-1">{run.error_message}</div>
      )}
    </div>
  );
}

// ── Proposed KPs panel ───────────────────────────────────────────────────────

function ProposedNodesPanel({
  items,
  diff,
  hasRun,
  runId,
  onApprove,
  isApproving,
}: {
  items: NodeTaggerProposedNode[];
  diff?: { added_node_count?: number; baseline_node_count?: number; expanded_node_count?: number };
  hasRun: boolean;
  runId?: number;
  onApprove: (nodeId: string, status: 'approved' | 'rejected') => void;
  isApproving: boolean;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!hasRun) {
    return (
      <div className="card p-4 text-sm text-text-muted">
        Run the tagger to propose new knowledge nodes for uncovered questions.
      </div>
    );
  }

  const sorted = [...items].sort((a, b) => (b.touch_count ?? 0) - (a.touch_count ?? 0));

  return (
    <div className="card p-3 text-sm max-h-[65vh] overflow-y-auto space-y-2">
      {diff && (
        <p className="text-xs text-text-muted">
          {diff.baseline_node_count} → {diff.expanded_node_count} nodes (+{diff.added_node_count}{' '}
          proposed)
        </p>
      )}
      {sorted.length === 0 ? (
        <p className="text-text-muted text-xs p-1">
          No new KPs proposed — all questions are covered by existing nodes.
        </p>
      ) : (
        sorted.map((node) => {
          const isOpen = expandedId === node.knowledge_node_id;
          const status = node.approval_status ?? 'pending';
          return (
            <ProposedNodeCard
              key={node.knowledge_node_id}
              node={node}
              isOpen={isOpen}
              status={status}
              onToggle={() => setExpandedId(isOpen ? null : node.knowledge_node_id)}
              onApprove={() => onApprove(node.knowledge_node_id, 'approved')}
              onReject={() => onApprove(node.knowledge_node_id, 'rejected')}
              isApproving={isApproving}
            />
          );
        })
      )}
    </div>
  );
}

function ProposedNodeCard({
  node,
  isOpen,
  status,
  onToggle,
  onApprove,
  onReject,
  isApproving,
}: {
  node: NodeTaggerProposedNode;
  isOpen: boolean;
  status: string;
  onToggle: () => void;
  onApprove: () => void;
  onReject: () => void;
  isApproving: boolean;
}) {
  const borderColor =
    status === 'approved'
      ? 'border-conf-covered/40 bg-conf-covered/5'
      : status === 'rejected'
        ? 'border-line/50 bg-bg-panel opacity-60'
        : 'border-status-needs/30 bg-status-needs/5';

  return (
    <div className={`rounded border p-2 ${borderColor}`}>
      {/* Header row */}
      <div className="flex items-start gap-2">
        <button
          type="button"
          className="flex-1 text-left"
          onClick={onToggle}
        >
          <div className="flex items-center gap-1.5">
            {isOpen ? (
              <ChevronDown className="w-3 h-3 text-text-dim shrink-0" />
            ) : (
              <ChevronRight className="w-3 h-3 text-text-dim shrink-0" />
            )}
            <span className="font-medium capitalize text-xs leading-snug">{node.label}</span>
          </div>
        </button>

        {/* Company count badge */}
        <span className="inline-flex items-center gap-0.5 shrink-0 rounded-full bg-amber-100 text-amber-800 text-[10px] font-semibold px-1.5 py-0.5">
          <Building2 className="w-2.5 h-2.5" />
          {node.touch_count ?? 0}
        </span>

        {/* Approve / Reject buttons — only if pending */}
        {status === 'pending' && (
          <div className="flex gap-1 shrink-0">
            <button
              type="button"
              title="Approve — save as canonical KP"
              className="w-6 h-6 rounded flex items-center justify-center bg-conf-covered/10 hover:bg-conf-covered/20 text-conf-covered"
              onClick={(e) => { e.stopPropagation(); onApprove(); }}
              disabled={isApproving}
            >
              <Check className="w-3 h-3" />
            </button>
            <button
              type="button"
              title="Reject"
              className="w-6 h-6 rounded flex items-center justify-center bg-conf-uncertain/10 hover:bg-conf-uncertain/20 text-conf-uncertain"
              onClick={(e) => { e.stopPropagation(); onReject(); }}
              disabled={isApproving}
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}
        {status === 'approved' && (
          <span className="text-[10px] text-conf-covered font-medium shrink-0">Approved ✓</span>
        )}
        {status === 'rejected' && (
          <span className="text-[10px] text-text-dim font-medium shrink-0">Rejected</span>
        )}
      </div>

      {/* Description */}
      <p className="text-[10px] text-text-muted mt-1 ml-4 line-clamp-2">{node.description}</p>

      {/* Expanded detail */}
      {isOpen && (
        <div className="mt-2 ml-4 space-y-2">
          {/* Companies */}
          {node.companies && node.companies.length > 0 && (
            <div>
              <div className="text-[9px] text-text-dim uppercase tracking-wide mb-1">Companies</div>
              <div className="flex flex-wrap gap-1">
                {node.companies.map((c) => (
                  <span
                    key={c}
                    className="text-[9px] rounded bg-amber-50 border border-amber-200 px-1 py-0.5 text-amber-700"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Questions that need this KP */}
          {node.question_previews && node.question_previews.length > 0 && (
            <div>
              <div className="text-[9px] text-text-dim uppercase tracking-wide mb-1">
                Questions needing this KP
              </div>
              <ul className="space-y-1">
                {node.question_previews.map((qp) => (
                  <li key={qp.row_key} className="flex gap-1 items-start">
                    <span className="chip text-[8px] shrink-0 mt-0.5">{qp.question_type}</span>
                    <span className="text-[10px] text-text line-clamp-2">{qp.question_text}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Graph info */}
          <div className="text-[9px] text-text-dim">
            depth {node.depth_level} · {node.prerequisites.length} prereq(s)
          </div>
        </div>
      )}
    </div>
  );
}

// ── Questions panel ──────────────────────────────────────────────────────────

function QuestionsPanel({
  items,
  hasRun,
}: {
  items: NodeTaggerQuestionResult[];
  hasRun: boolean;
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  if (!hasRun) {
    return (
      <div className="card p-4 text-sm text-text-muted">
        Run the tagger to see per-question KP tagging results.
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="card p-4 text-sm text-text-muted">
        No questions processed yet in this run.
      </div>
    );
  }

  return (
    <div className="card p-3 text-sm max-h-[65vh] overflow-y-auto space-y-2">
      {items.map((q) => {
        const isOpen = expandedKey === q.row_key;
        const coverageBg =
          q.coverage_status === 'full'
            ? 'bg-conf-covered/10 text-conf-covered border-conf-covered/30'
            : q.coverage_status === 'partial'
              ? 'bg-amber-50 text-amber-700 border-amber-200'
              : q.coverage_status === 'none'
                ? 'bg-conf-uncertain/10 text-conf-uncertain border-conf-uncertain/30'
                : 'bg-bg-panel text-text-dim border-line';

        return (
          <div key={q.row_key} className="rounded border border-line bg-bg-panel p-2">
            <button
              type="button"
              className="w-full text-left"
              onClick={() => setExpandedKey(isOpen ? null : q.row_key)}
            >
              <div className="flex items-start gap-2">
                {isOpen ? (
                  <ChevronDown className="w-3 h-3 text-text-dim shrink-0 mt-0.5" />
                ) : (
                  <ChevronRight className="w-3 h-3 text-text-dim shrink-0 mt-0.5" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap mb-1">
                    <span className="chip text-[9px]">{q.question_type}</span>
                    {q.coverage_status && (
                      <span className={`text-[9px] rounded border px-1 py-0.5 font-medium ${coverageBg}`}>
                        {q.coverage_status}
                      </span>
                    )}
                    {q.error_message && (
                      <span className="text-[9px] text-conf-uncertain">error</span>
                    )}
                  </div>
                  <p className="text-xs text-text line-clamp-2">{q.question_text}</p>
                </div>
              </div>
            </button>

            {isOpen && (
              <div className="mt-2 ml-5 space-y-2">
                {/* Existing nodes matched */}
                {q.existing_node_labels && q.existing_node_labels.length > 0 && (
                  <div>
                    <div className="text-[9px] text-text-dim uppercase tracking-wide mb-1">
                      Existing KPs matched
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {q.existing_node_labels.map((lbl) => (
                        <span
                          key={lbl}
                          className="text-[9px] rounded bg-conf-covered/10 border border-conf-covered/30 px-1 py-0.5 text-conf-covered capitalize"
                        >
                          {lbl}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* New nodes proposed */}
                {q.new_node_labels && q.new_node_labels.length > 0 && (
                  <div>
                    <div className="text-[9px] text-text-dim uppercase tracking-wide mb-1">
                      New KPs proposed
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {q.new_node_labels.map((lbl) => (
                        <span
                          key={lbl}
                          className="text-[9px] rounded bg-amber-50 border border-amber-200 px-1 py-0.5 text-amber-700 capitalize"
                        >
                          {lbl}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* No new nodes, full coverage */}
                {q.coverage_status === 'full' &&
                  (!q.new_node_labels || q.new_node_labels.length === 0) && (
                    <p className="text-[10px] text-conf-covered">
                      Fully covered by existing KPs — no new nodes needed.
                    </p>
                  )}

                {q.error_message && (
                  <p className="text-[10px] text-conf-uncertain">{q.error_message}</p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Approved canonical nodes panel ───────────────────────────────────────────

function ApprovedPanel({ nodes }: { nodes: NodeTaggerCanonicalNode[] }) {
  if (nodes.length === 0) {
    return (
      <div className="card p-4 text-sm text-text-muted">
        No approved canonical KPs yet. Approve proposed KPs in the "Proposed KPs" tab — they'll
        appear here and be reused in future tagger runs.
      </div>
    );
  }

  return (
    <div className="card p-3 text-sm max-h-[65vh] overflow-y-auto space-y-2">
      <p className="text-xs text-text-muted">
        {nodes.length} approved canonical KP(s) — included in graph context for all future runs.
      </p>
      {nodes.map((node) => (
        <div
          key={node.knowledge_node_id}
          className="rounded border border-conf-covered/30 bg-conf-covered/5 p-2"
        >
          <div className="flex items-start justify-between gap-2">
            <span className="font-medium capitalize text-xs">{node.label}</span>
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="text-[9px] rounded bg-conf-covered/10 border border-conf-covered/30 px-1 py-0.5 text-conf-covered">
                depth {node.depth_level}
              </span>
              <span className="text-[9px] text-conf-covered font-medium">Approved ✓</span>
            </div>
          </div>
          <p className="text-[10px] text-text-muted mt-1 line-clamp-2">{node.description}</p>
          <div className="text-[9px] text-text-dim mt-1">
            approved {new Date(node.approved_at).toLocaleDateString()}
            {node.source_run_id != null && ` · from run #${node.source_run_id}`}
          </div>
        </div>
      ))}
    </div>
  );
}
