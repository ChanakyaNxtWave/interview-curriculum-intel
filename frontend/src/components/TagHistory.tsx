import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { History, Loader2, X } from 'lucide-react';
import { fetchHistory } from '../api/theory';
import VerdictBadge from './VerdictBadge';
import ConfidenceBar from './ConfidenceBar';
import type { TagHistoryEntry } from '../api/types';

export default function TagHistory({ rowKey }: { rowKey: string }) {
  const [selected, setSelected] = useState<TagHistoryEntry | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ['tag-history', rowKey],
    queryFn: () => fetchHistory(rowKey),
  });

  const items = data?.items ?? [];

  return (
    <div className="card p-4 mt-4">
      <div className="flex items-center gap-2 mb-3">
        <History className="w-4 h-4 text-brand" />
        <h2 className="font-semibold text-text">Tag history</h2>
        <span className="text-xs text-text-dim">
          {items.length} snapshot{items.length === 1 ? '' : 's'} across prompt versions
        </span>
      </div>

      {isLoading && (
        <div className="text-text-muted text-sm flex items-center gap-1.5">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-brand" /> Loading history…
        </div>
      )}
      {error && <div className="text-conf-uncertain text-sm">{String(error)}</div>}
      {!isLoading && items.length === 0 && (
        <div className="text-text-muted text-sm">No history yet. Click <em>Re-tag now</em> to record a snapshot.</div>
      )}

      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-dim text-xs uppercase tracking-wide">
                <th className="py-2 pr-3">When</th>
                <th className="py-2 pr-3">Version</th>
                <th className="py-2 pr-3">Verdict</th>
                <th className="py-2 pr-3">Confidence</th>
                <th className="py-2 pr-3">KPs</th>
                <th className="py-2 pr-3">Cites</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((h) => (
                <tr key={h.id} className="border-t border-line">
                  <td className="py-2 pr-3 text-text-muted text-xs">
                    {new Date(h.created_at).toLocaleString()}
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">{h.prompt_version}</td>
                  <td className="py-2 pr-3">
                    <VerdictBadge verdict={h.verdict} />
                  </td>
                  <td className="py-2 pr-3 min-w-[140px]">
                    <ConfidenceBar value={h.overall_confidence} />
                  </td>
                  <td className="py-2 pr-3 tabular-nums">{h.required_kps?.length ?? 0}</td>
                  <td className="py-2 pr-3 tabular-nums">{h.citations?.length ?? 0}</td>
                  <td className="py-2 pr-3">
                    <button
                      className="btn text-xs"
                      onClick={() => setSelected(h)}
                    >
                      View reasoning
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && <SnapshotModal entry={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function SnapshotModal({
  entry,
  onClose,
}: {
  entry: TagHistoryEntry;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="card max-w-3xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-line sticky top-0 bg-bg-card">
          <div>
            <h3 className="font-semibold text-text">Snapshot · {entry.prompt_version}</h3>
            <div className="text-xs text-text-dim mt-0.5">
              {new Date(entry.created_at).toLocaleString()}
            </div>
          </div>
          <button onClick={onClose} className="text-text-dim hover:text-text" aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-4">
          <div className="flex items-center gap-3">
            <VerdictBadge verdict={entry.verdict} />
            <ConfidenceBar value={entry.overall_confidence} />
          </div>
          {entry.kp_identifier_reasoning && (
            <Block title="KP identification reasoning">
              {entry.kp_identifier_reasoning}
            </Block>
          )}
          {entry.judge_reasoning && (
            <Block title="Coverage judge reasoning">{entry.judge_reasoning}</Block>
          )}
          {entry.rationale && <Block title="Final rationale">{entry.rationale}</Block>}
          {entry.required_kps?.length > 0 && (
            <div>
              <div className="text-xs text-text-dim uppercase tracking-wide mb-1">
                Required KPs
              </div>
              <ul className="text-sm text-text-muted space-y-1">
                {entry.required_kps.map((k) => (
                  <li key={k.source_kp_id}>
                    <span className="font-mono text-brand mr-2">{k.source_kp_id}</span>
                    {k.rationale}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entry.citations?.length > 0 && (
            <div>
              <div className="text-xs text-text-dim uppercase tracking-wide mb-1">
                Accepted citations
              </div>
              <ul className="text-sm text-text-muted space-y-1">
                {entry.citations.map((c) => (
                  <li key={c.content_id}>
                    {c.title} <span className="text-text-dim">({c.kp_id})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entry.review_reasons?.length > 0 && (
            <div>
              <div className="text-xs text-text-dim uppercase tracking-wide mb-1">
                Review flags
              </div>
              <ul className="text-sm text-text-muted list-disc list-inside">
                {entry.review_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-text-dim uppercase tracking-wide mb-1">{title}</div>
      <div className="rounded-md border border-line bg-bg-panel p-3 text-sm text-text whitespace-pre-wrap leading-relaxed">
        {children}
      </div>
    </div>
  );
}
