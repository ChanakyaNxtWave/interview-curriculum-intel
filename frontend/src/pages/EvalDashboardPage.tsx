import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowRight,
  GitCommitVertical,
  Play,
  RotateCw,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import {
  activateVersion,
  fetchEvalRuns,
  fetchImprovementSummary,
  fetchPromptVersions,
  recompile,
  runEvalNow,
} from '../api/theory';
import CourseTabs from '../components/CourseTabs';
import type { ImprovementSummary } from '../api/types';

export default function EvalDashboardPage() {
  const qc = useQueryClient();
  const versionsQ = useQuery({
    queryKey: ['theory-versions'],
    queryFn: fetchPromptVersions,
    refetchInterval: 10_000,
  });
  const runsQ = useQuery({
    queryKey: ['theory-runs'],
    queryFn: () => fetchEvalRuns(20),
    refetchInterval: 10_000,
  });
  const summaryQ = useQuery({
    queryKey: ['theory-improvement'],
    queryFn: fetchImprovementSummary,
    refetchInterval: 15_000,
  });

  const evalNow = useMutation({
    mutationFn: runEvalNow,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['theory-runs'] });
    },
  });
  const recomp = useMutation({
    mutationFn: recompile,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['theory-versions'] });
      qc.invalidateQueries({ queryKey: ['theory-runs'] });
    },
  });
  const activate = useMutation({
    mutationFn: (id: number) => activateVersion(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['theory-versions'] });
    },
  });

  const versions = versionsQ.data?.items ?? [];
  const runs = runsQ.data?.items ?? [];

  return (
    <div>
      <CourseTabs />
      <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
        <div className="flex items-center gap-2">
          <GitCommitVertical className="w-5 h-5 text-brand" />
          <h1 className="text-xl font-semibold">Eval Dashboard</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn disabled:opacity-50"
            disabled={evalNow.isPending}
            onClick={() => evalNow.mutate()}
          >
            <Play className={`w-3.5 h-3.5 ${evalNow.isPending ? 'animate-spin' : ''}`} />
            Run eval now
          </button>
          <button
            className="btn-primary disabled:opacity-50"
            disabled={recomp.isPending}
            onClick={() => recomp.mutate()}
          >
            <RotateCw className={`w-3.5 h-3.5 ${recomp.isPending ? 'animate-spin' : ''}`} />
            Recompile DSPy
          </button>
        </div>
      </div>

      {recomp.isError && (
        <div className="mb-3 p-3 rounded-md border border-conf-uncertain/40 bg-conf-uncertain/10 text-sm text-conf-uncertain">
          {String(recomp.error)}
        </div>
      )}
      {recomp.isSuccess && (
        <div className="mb-3 p-3 rounded-md border border-conf-high/40 bg-conf-high/10 text-sm text-conf-high">
          Compiled {recomp.data.version} (
          {recomp.data.activated ? 'activated' : 'logged only — below gate'}) · devset agreement{' '}
          {(recomp.data.devset_agreement * 100).toFixed(1)}%
        </div>
      )}
      {evalNow.isSuccess && (
        <div className="mb-3 p-3 rounded-md border border-conf-high/40 bg-conf-high/10 text-sm text-conf-high">
          Eval done on version {evalNow.data.version} · agreement{' '}
          {(evalNow.data.metrics.agreement_rate * 100).toFixed(1)}% ({evalNow.data.devset_size}{' '}
          dev examples)
        </div>
      )}

      {summaryQ.data && <ImprovementCard data={summaryQ.data} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div className="card p-4">
          <h2 className="font-semibold text-text mb-3">Prompt versions</h2>
          {versions.length === 0 ? (
            <div className="text-text-muted text-sm">No compiled versions yet.</div>
          ) : (
            <div className="space-y-2">
              {versions.map((v) => (
                <div
                  key={v.id}
                  className={`p-3 rounded-md border ${
                    v.is_active ? 'border-brand/50 bg-brand/5' : 'border-line bg-bg-panel'
                  }`}
                >
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="font-mono text-sm">{normalizeVersionName(v.version)}</div>
                    <div className="flex items-center gap-2">
                      {v.is_active ? (
                        <span className="chip-on">active</span>
                      ) : (
                        <button
                          className="btn"
                          onClick={() => activate.mutate(v.id)}
                          disabled={activate.isPending}
                        >
                          <ArrowRight className="w-3.5 h-3.5" /> Activate
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-text-muted flex flex-wrap gap-2">
                    <span>gold: {v.gold_count_at_compile}</span>
                    <span>·</span>
                    <span>demos: {v.fewshot_count}</span>
                    {v.devset_agreement != null && (
                      <>
                        <span>·</span>
                        <span>
                          devset:{' '}
                          {v.devset_agreement >= 0.85 ? (
                            <CheckCircle2 className="w-3 h-3 inline text-conf-high" />
                          ) : (
                            <AlertCircle className="w-3 h-3 inline text-conf-medium" />
                          )}{' '}
                          {(v.devset_agreement * 100).toFixed(0)}%
                        </span>
                      </>
                    )}
                  </div>
                  {v.notes && <p className="text-xs text-text-dim mt-1">{v.notes}</p>}
                  <div className="text-[11px] text-text-dim mt-1">
                    {new Date(v.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card p-4">
          <h2 className="font-semibold text-text mb-3">Recent eval runs</h2>
          {runs.length === 0 ? (
            <div className="text-text-muted text-sm">No runs yet.</div>
          ) : (
            <div className="space-y-2">
              {runs.map((r) => (
                <div key={r.id} className="p-3 rounded-md border border-line bg-bg-panel">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="font-mono text-xs text-text-muted">
                      {normalizeVersionName(r.prompt_version)} · {r.trigger}
                    </div>
                    <span
                      className={`chip ${
                        r.agreement_rate >= 0.85 ? 'chip-on' : ''
                      }`}
                    >
                      {(r.agreement_rate * 100).toFixed(1)}% agree
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-text-muted">
                    n={r.total} · jaccard {(r.kp_jaccard_avg * 100).toFixed(0)}% · conf{' '}
                    {(r.avg_confidence * 100).toFixed(0)}% · false-cov {r.false_covered} ·
                    false-not {r.false_not_covered}
                  </div>
                  <div className="text-[11px] text-text-dim mt-1">
                    {new Date(r.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ImprovementCard({ data }: { data: ImprovementSummary }) {
  const trend = data.trend;
  return (
    <div className="card p-4 mb-4">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
        <h2 className="font-semibold text-text">Improvement vs latest gold</h2>
        <div className="flex items-center gap-2 text-xs">
          <span className="chip">{data.total_golds} golds</span>
          <span className="chip">{data.rows_with_history} rows w/ history</span>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Stat label="Fixed by latest" value={data.fixed} cls="text-conf-high" />
        <Stat label="Regressed" value={data.regressed} cls="text-conf-uncertain" />
        <Stat label="Trend points" value={trend.length} cls="text-text" />
      </div>
      {trend.length > 0 ? (
        <TrendChart trend={trend} />
      ) : (
        <div className="text-sm text-text-muted">No eval runs yet.</div>
      )}
    </div>
  );
}

function Stat({ label, value, cls }: { label: string; value: number; cls: string }) {
  return (
    <div className="rounded-md border border-line bg-bg-panel p-3">
      <div className="text-xs text-text-dim">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${cls}`}>{value}</div>
    </div>
  );
}

function TrendChart({ trend }: { trend: ImprovementSummary['trend'] }) {
  const w = 600;
  const h = 120;
  const pad = 24;
  const n = trend.length;
  if (n === 0) return null;
  const xs = trend.map((_, i) => pad + (i * (w - 2 * pad)) / Math.max(1, n - 1));
  const ys = trend.map((t) => h - pad - t.agreement_rate * (h - 2 * pad));
  const path = xs
    .map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${ys[i].toFixed(1)}`)
    .join(' ');
  const gate = h - pad - 0.85 * (h - 2 * pad);
  return (
    <div className="overflow-x-auto">
      <svg width={w} height={h} className="block">
        {[0, 0.25, 0.5, 0.75, 1].map((g) => {
          const y = h - pad - g * (h - 2 * pad);
          return (
            <g key={g}>
              <line x1={pad} x2={w - pad} y1={y} y2={y} stroke="#2a2f3f" strokeDasharray="2 4" />
              <text x={4} y={y + 3} fill="#6b7280" fontSize={10}>
                {(g * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}
        <line
          x1={pad}
          x2={w - pad}
          y1={gate}
          y2={gate}
          stroke="#22c55e"
          strokeDasharray="4 4"
          opacity={0.6}
        />
        <text x={w - pad - 28} y={gate - 4} fill="#22c55e" fontSize={10}>
          gate 85%
        </text>
        <path d={path} stroke="#7c9cff" strokeWidth={2} fill="none" />
        {xs.map((x, i) => (
          <g key={i}>
            <circle cx={x} cy={ys[i]} r={3.5} fill="#7c9cff" />
            <title>
              {normalizeVersionName(trend[i].prompt_version)} · {(trend[i].agreement_rate * 100).toFixed(1)}% ·{' '}
              {trend[i].trigger} · {new Date(trend[i].created_at).toLocaleString()}
            </title>
          </g>
        ))}
      </svg>
    </div>
  );
}

function normalizeVersionName(version: string) {
  if (!version) return version;
  return version.replace(/^theory-/, 'eval-');
}
