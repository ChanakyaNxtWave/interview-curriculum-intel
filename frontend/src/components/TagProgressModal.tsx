import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Loader2, AlertCircle, Clock, Sparkles, X, ChevronDown } from 'lucide-react';
import { fetchActiveContext, fetchTagStatus, type TagProgress } from '../api/theory';
import { fetchCodingTagStatus } from '../api/coding';

const STAGE_ORDER = [
  'start',
  'load_active_prompt',
  'identify_kps',
  'kps_done',
  'retrieve_citations',
  'citations_done',
  'judge_coverage',
  'judge_done',
  'synthesize_answer',
  'synthesize_done',
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
    sub: 'Pull approved KP-tagged content (reading or coding)',
  },
  citations_done: { label: 'Citation candidates ready', sub: 'Deduped, ranked, full bodies attached' },
  judge_coverage: {
    label: 'Judge coverage (LLM call #2)',
    sub: 'DSPy JudgeCoverage · ChainOfThought',
  },
  judge_done: { label: 'Verdict decided', sub: 'Confidence + accepted citations returned' },
  synthesize_answer: {
    label: 'Synthesize answer (LLM call #3)',
    sub: 'DSPy AnswerQuestion · mandatory for every question',
  },
  synthesize_done: {
    label: 'Answer produced',
    sub: 'synthesis_quality: complete | insufficient',
  },
  gating: {
    label: 'Human review gate',
    sub: 'AI output saved; approved/rejected only via human review',
  },
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
  /** Poll tag-status while the backend pipeline runs (after POST returns). */
  tracking: boolean;
  isCoding?: boolean;
  onClose: () => void;
  onComplete?: () => void;
}

export default function TagProgressModal({
  rowKey,
  questionText,
  open,
  tracking,
  isCoding = false,
  onClose,
  onComplete,
}: Props) {
  const [elapsedMs, setElapsedMs] = useState(0);
  const [showContext, setShowContext] = useState(false);
  const completedRef = useRef(false);

  const ctxQ = useQuery({
    queryKey: ['eval-active-context'],
    queryFn: fetchActiveContext,
    enabled: open,
    staleTime: 30_000,
  });

  const statusQ = useQuery<TagProgress>({
    queryKey: ['tag-status', rowKey, isCoding],
    queryFn: () => (isCoding ? fetchCodingTagStatus(rowKey) : fetchTagStatus(rowKey)),
    enabled: open && !!rowKey && tracking,
    refetchInterval: open && tracking ? 500 : false,
  });

  useEffect(() => {
    if (!open || !tracking) return;
    completedRef.current = false;
    const start = Date.now();
    setElapsedMs(0);
    const id = setInterval(() => setElapsedMs(Date.now() - start), 200);
    return () => clearInterval(id);
  }, [open, tracking, rowKey]);

  const status = statusQ.data;
  const currentIdx = stageIdx(status?.stage ?? 'start');
  const isError = status?.stage === 'error' || !!status?.error;
  const pipelineDone =
    status?.completed === true || status?.stage === 'done' || status?.stage === 'error';
  const isRunning = tracking && !pipelineDone;

  useEffect(() => {
    if (!tracking || !pipelineDone || completedRef.current) return;
    completedRef.current = true;
    onComplete?.();
  }, [tracking, pipelineDone, onComplete]);

  const completedSet = useMemo(() => {
    const set = new Set<string>();
    for (const ev of status?.events ?? []) set.add(ev.stage);
    return set;
  }, [status]);

  if (!open) return null;

  const ctx = ctxQ.data;
  const apv = ctx?.active_prompt_version;
  const displayElapsed = isRunning ? elapsedMs : status?.elapsed_ms ?? elapsedMs;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isRunning) onClose();
      }}
    >
      <div className="bg-bg-panel border border-line rounded-lg shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-line">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-brand" />
            <h2 className="text-lg font-semibold">
              {isRunning
                ? 'Tagging in progress…'
                : isError
                ? 'Tagging failed'
                : 'Tag complete'}
            </h2>
            {!isRunning && !isError && status?.result?.verdict && (
              <span className="chip-on">
                <CheckCircle2 className="w-3 h-3" /> {status.result.verdict}
              </span>
            )}
          </div>
          <button
            className="text-text-muted hover:text-text"
            onClick={onClose}
            disabled={isRunning}
          >
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

          {status?.stage === 'idle' && tracking && (
            <div className="text-sm text-text-muted flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-brand" />
              Starting pipeline…
            </div>
          )}

          <div className="card bg-bg/40 overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-text-muted uppercase tracking-wide hover:bg-bg-hover"
              onClick={() => setShowContext((v) => !v)}
            >
              What this re-tag considers
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform ${showContext ? '' : '-rotate-90'}`}
              />
            </button>
            {showContext && (
              <div className="px-3 pb-3">
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
            )}
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                Pipeline stages
              </div>
              <div className="flex items-center gap-1 text-xs text-text-muted">
                <Clock className="w-3 h-3" />
                {(displayElapsed / 1000).toFixed(1)}s
                {status?.trigger && <span className="ml-2 chip">{status.trigger}</span>}
              </div>
            </div>
            <ol className="space-y-1">
              {STAGE_ORDER.map((s, i) => {
                const done = completedSet.has(s) || i < currentIdx;
                const current = i === currentIdx && isRunning && !isError;
                const errored = isError && (i === currentIdx || s === 'done');
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
                    {s === 'kps_done' && (status?.kps_count ?? 0) > 0 && (
                      <span className="chip">{status!.kps_count} KPs</span>
                    )}
                    {s === 'citations_done' && (status?.candidates_count ?? 0) > 0 && (
                      <span className="chip">{status!.candidates_count} candidates</span>
                    )}
                    {s === 'judge_done' && status?.verdict && (
                      <span className="chip-on">
                        {status.verdict} · {((status.confidence ?? 0) * 100).toFixed(0)}%
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

          {!isRunning && status?.result && (
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
          {!isRunning && (
            <button className="btn btn-primary" onClick={onClose}>
              Close
            </button>
          )}
          {isRunning && (
            <span className="text-xs text-text-muted self-center">
              Pipeline running — stages update live (~30–60s typical)
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
