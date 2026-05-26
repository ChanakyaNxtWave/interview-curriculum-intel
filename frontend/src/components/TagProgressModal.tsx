import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Loader2, AlertCircle, Clock, Sparkles, X } from 'lucide-react';
import { fetchActiveContext, fetchTagStatus } from '../api/theory';
import type { TagProgress } from '../api/theory';

const STAGE_ORDER = [
  'start',
  'load_active_prompt',
  'identify_kps',
  'kps_done',
  'retrieve_citations',
  'citations_done',
  'judge_coverage',
  'judge_done',
  'gating',
  'persisting',
  'done',
] as const;

type Stage = (typeof STAGE_ORDER)[number];

const STAGE_LABELS: Record<Stage, { label: string; sub: string }> = {
  start: { label: 'Queued', sub: 'Tagging request received' },
  load_active_prompt: {
    label: 'Load compiled prompt',
    sub: 'Active DSPy version + fewshot demos applied',
  },
  identify_kps: {
    label: 'Identify KPs (LLM call #1)',
    sub: 'DSPy IdentifyKPs · ChainOfThought · Sonnet 4.5',
  },
  kps_done: { label: 'KPs picked', sub: 'Required knowledge points extracted' },
  retrieve_citations: {
    label: 'Retrieve citations (SQL)',
    sub: 'Pull approved KP-tagged content',
  },
  citations_done: { label: 'Citation candidates ready', sub: 'Deduped, ranked, snippets attached' },
  judge_coverage: {
    label: 'Judge coverage (LLM call #2)',
    sub: 'DSPy JudgeCoverage · ChainOfThought',
  },
  judge_done: { label: 'Verdict decided', sub: 'Confidence + accepted citations returned' },
  gating: { label: 'Auto-approve gate', sub: 'conf ≥ 0.85 → approved · else needs_review' },
  persisting: { label: 'Persist tag', sub: 'Save tag row + history snapshot' },
  done: { label: 'Done', sub: 'Result available' },
};

function stageIdx(s: string): number {
  const i = (STAGE_ORDER as readonly string[]).indexOf(s);
  return i < 0 ? -1 : i;
}

interface Props {
  rowKey: string;
  questionText?: string;
  open: boolean;
  active: boolean; // true while POST in flight
  onClose: () => void;
}

export default function TagProgressModal({
  rowKey,
  questionText,
  open,
  active,
  onClose,
}: Props) {
  const [elapsedMs, setElapsedMs] = useState(0);
  const ctxQ = useQuery({
    queryKey: ['theory-active-context'],
    queryFn: fetchActiveContext,
    enabled: open,
    staleTime: 30_000,
  });
  const statusQ = useQuery<TagProgress>({
    queryKey: ['tag-status', rowKey],
    queryFn: () => fetchTagStatus(rowKey),
    enabled: open && !!rowKey,
    refetchInterval: open && active ? 700 : false,
  });

  // Local ticking elapsed counter while POST is in flight
  useEffect(() => {
    if (!open || !active) return;
    const start = Date.now();
    setElapsedMs(0);
    const id = setInterval(() => setElapsedMs(Date.now() - start), 200);
    return () => clearInterval(id);
  }, [open, active, rowKey]);

  const status = statusQ.data;
  const currentIdx = stageIdx(status?.stage ?? 'start');
  const isError = status?.stage === 'error' || !!status?.error;
  const isDone = !active && (status?.completed || status?.stage === 'done');

  const completedSet = useMemo(() => {
    const set = new Set<string>();
    for (const ev of status?.events ?? []) set.add(ev.stage);
    return set;
  }, [status]);

  if (!open) return null;

  const ctx = ctxQ.data;
  const apv = ctx?.active_prompt_version;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && !active) onClose();
      }}
    >
      <div className="bg-bg-panel border border-line rounded-lg shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-line">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-brand" />
            <h2 className="text-lg font-semibold">
              {active ? 'Tagging in progress…' : isError ? 'Tagging failed' : 'Tag complete'}
            </h2>
            {!active && !isError && (
              <span className="chip-on">
                <CheckCircle2 className="w-3 h-3" /> {status?.result?.verdict}
              </span>
            )}
          </div>
          <button className="text-text-muted hover:text-text" onClick={onClose} disabled={active}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto space-y-4">
          {questionText && (
            <div className="text-sm text-text-muted">
              <span className="font-medium text-text">Q:</span> {questionText.slice(0, 200)}
              {questionText.length > 200 ? '…' : ''}
            </div>
          )}

          <div className="card p-3 bg-bg/40">
            <div className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
              What this re-tag considers
            </div>
            {ctxQ.isLoading ? (
              <div className="text-sm text-text-muted">Loading context…</div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <Stat
                  label="Active prompt"
                  value={apv?.version ?? 'uninitialized'}
                  sub={apv ? `compiled ${new Date(apv.created_at).toLocaleDateString()}` : ''}
                />
                <Stat
                  label="Few-shot demos"
                  value={String(apv?.fewshot_count ?? 0)}
                  sub="bootstrapped from gold"
                />
                <Stat
                  label="Gold set"
                  value={String(ctx?.gold_set_total ?? 0)}
                  sub={`@ compile: ${apv?.gold_count_at_compile ?? 0}`}
                />
                <Stat
                  label="Reviewer feedback"
                  value={String(ctx?.feedback_total ?? 0)}
                  sub={Object.entries(ctx?.feedback_by_severity ?? {})
                    .map(([k, v]) => `${k}:${v}`)
                    .join(' · ')}
                />
                <Stat
                  label="Dev agreement"
                  value={
                    apv?.devset_agreement != null
                      ? `${(apv.devset_agreement * 100).toFixed(0)}%`
                      : 'n/a'
                  }
                  sub="on holdout golds"
                />
                <Stat
                  label="KP catalog"
                  value={String(ctx?.kp_catalog_size ?? 0)}
                  sub={ctx?.model ?? ''}
                />
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                Pipeline stages
              </div>
              <div className="flex items-center gap-1 text-xs text-text-muted">
                <Clock className="w-3 h-3" />
                {(((active ? elapsedMs : status?.elapsed_ms) ?? 0) / 1000).toFixed(1)}s
                {status?.trigger && (
                  <span className="ml-2 chip">{status.trigger}</span>
                )}
              </div>
            </div>
            <ol className="space-y-1">
              {STAGE_ORDER.map((s, i) => {
                const done = completedSet.has(s) || i < currentIdx;
                const current = i === currentIdx && !isDone && !isError;
                const errored = isError && i === currentIdx;
                return (
                  <li
                    key={s}
                    className={`flex items-start gap-2 p-2 rounded ${
                      current
                        ? 'bg-brand/10 border border-brand/30'
                        : done
                        ? 'opacity-70'
                        : 'opacity-40'
                    }`}
                  >
                    <span className="mt-0.5">
                      {errored ? (
                        <AlertCircle className="w-4 h-4 text-conf-uncertain" />
                      ) : done ? (
                        <CheckCircle2 className="w-4 h-4 text-conf-covered" />
                      ) : current ? (
                        <Loader2 className="w-4 h-4 animate-spin text-brand" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border border-line" />
                      )}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm">{STAGE_LABELS[s].label}</div>
                      <div className="text-xs text-text-muted">{STAGE_LABELS[s].sub}</div>
                    </div>
                    {/* per-stage metric chips */}
                    {s === 'kps_done' && status?.kps_count != null && (
                      <span className="chip">{status.kps_count} KPs</span>
                    )}
                    {s === 'citations_done' && status?.candidates_count != null && (
                      <span className="chip">{status.candidates_count} candidates</span>
                    )}
                    {s === 'judge_done' && status?.verdict && (
                      <span className="chip-on">
                        {status.verdict} ·{' '}
                        {((status.confidence ?? 0) * 100).toFixed(0)}%
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          </div>

          {isError && (
            <div className="card p-3 border border-conf-uncertain/40 bg-conf-uncertain/5">
              <div className="text-xs font-semibold text-conf-uncertain uppercase tracking-wide mb-1">
                Error
              </div>
              <div className="text-sm break-words">{status?.error}</div>
            </div>
          )}

          {!active && status?.result && (
            <div className="card p-3 bg-bg/40">
              <div className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
                Result
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <Stat label="Verdict" value={status.result.verdict ?? '—'} />
                <Stat
                  label="Confidence"
                  value={`${((status.result.overall_confidence ?? 0) * 100).toFixed(0)}%`}
                />
                <Stat label="Status" value={status.result.review_status ?? '—'} />
                <Stat
                  label="Cited / candidates"
                  value={`${status.result.citations_count ?? 0} / ${
                    status.result.candidate_citations_count ?? 0
                  }`}
                />
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-line p-3 flex justify-end gap-2">
          {!active && (
            <button className="btn btn-primary" onClick={onClose}>
              Close
            </button>
          )}
          {active && (
            <span className="text-xs text-text-muted self-center">
              LLM call running… ~30–60s typical
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-text-muted">{label}</div>
      <div className="text-text font-medium truncate" title={value}>
        {value}
      </div>
      {sub && <div className="text-text-dim text-[10px] truncate">{sub}</div>}
    </div>
  );
}
