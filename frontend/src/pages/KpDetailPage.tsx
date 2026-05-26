import { useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, FileText, Code2, FolderGit2, Filter } from 'lucide-react';
import { fetchMappings } from '../api/mappings';
import { fetchKpsWithCounts } from '../api/kps';
import SearchBox from '../components/SearchBox';
import EmptyState from '../components/EmptyState';
import ConfidenceBadge from '../components/ConfidenceBadge';
import ReviewStatusBadge from '../components/ReviewStatusBadge';
import { useDebounce } from '../hooks/useDebounce';
import type { ConfidenceLevel, ReviewStatus } from '../api/types';

const TYPE_ICON: Record<string, React.ReactNode> = {
  reading_material: <FileText className="w-4 h-4" />,
  coding_question: <Code2 className="w-4 h-4" />,
  project: <FolderGit2 className="w-4 h-4" />,
};

export default function KpDetailPage() {
  const { courseId = '', kpId = '' } = useParams();
  const [sp, setSp] = useSearchParams();
  const q = sp.get('q') ?? '';
  const contentType = sp.get('type') ?? '';
  const reviewStatus = sp.get('status') ?? '';
  const confidence = sp.get('conf') ?? '';
  const tagSource = sp.get('source') ?? 'both';
  const [localQ, setLocalQ] = useState(q);
  const debouncedQ = useDebounce(localQ, 300);

  useMemo(() => {
    if (debouncedQ !== q) {
      const next = new URLSearchParams(sp);
      if (debouncedQ) next.set('q', debouncedQ);
      else next.delete('q');
      setSp(next, { replace: true });
    }
  }, [debouncedQ]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data: kpData } = useQuery({
    queryKey: ['kp-meta', kpId],
    queryFn: () => fetchKpsWithCounts({ course_id: courseId }),
    select: (d) => d.knowledge_points.find((k) => k.source_kp_id === kpId),
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['mappings', kpId, contentType, reviewStatus, confidence, debouncedQ],
    queryFn: () =>
      fetchMappings({
        kp_id: kpId,
        content_type: contentType || undefined,
        review_status: reviewStatus || undefined,
        confidence: confidence || undefined,
        q: debouncedQ || undefined,
        limit: 500,
      }),
  });

  const items = useMemo(() => {
    const rows = data?.items ?? [];
    if (tagSource === 'both') return rows;
    return rows.filter((m) => {
      const aiHit = m.ai_result?.proposed_tags?.some((t) => t.source_kp_id === kpId);
      const humanHit = m.human_tags?.some((t) => t.source_kp_id === kpId);
      if (tagSource === 'ai') return aiHit;
      if (tagSource === 'human') return humanHit;
      return true;
    });
  }, [data, tagSource, kpId]);

  function setParam(key: string, val: string) {
    const next = new URLSearchParams(sp);
    if (val) next.set(key, val);
    else next.delete(key);
    setSp(next, { replace: true });
  }

  function clearAll() {
    setLocalQ('');
    setSp(new URLSearchParams(), { replace: true });
  }

  return (
    <div>
      <div className="mb-4">
        <Link
          to={`/courses/${courseId}`}
          className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text"
        >
          <ArrowLeft className="w-4 h-4" /> Back to KPs
        </Link>
      </div>

      <div className="card p-5 mb-4">
        <div className="flex items-start gap-3 flex-wrap">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold text-text">{kpData?.label ?? kpId}</h1>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className="font-mono text-xs text-text-dim">{kpId}</span>
              {kpData?.label_enum && <span className="chip">{kpData.label_enum}</span>}
            </div>
            {kpData?.description && (
              <p className="text-text-muted text-sm mt-3 leading-relaxed">{kpData.description}</p>
            )}
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold tabular-nums text-text">
              {kpData?.mapped_content_count ?? items.length}
            </div>
            <div className="text-xs text-text-dim">mapped content</div>
          </div>
        </div>
      </div>

      <div className="card p-3 mb-4 flex flex-wrap items-center gap-2">
        <SearchBox value={localQ} onChange={setLocalQ} placeholder="Search title or topic…" />
        <Select value={contentType} onChange={(v) => setParam('type', v)}>
          <option value="">Type: any</option>
          <option value="reading_material">Reading material</option>
          <option value="coding_question">Coding question</option>
          <option value="project">Project</option>
        </Select>
        <Select value={reviewStatus} onChange={(v) => setParam('status', v)}>
          <option value="">Status: any</option>
          <option value="pending">pending</option>
          <option value="needs_review">needs review</option>
          <option value="approved">approved</option>
          <option value="rejected">rejected</option>
        </Select>
        <Select value={confidence} onChange={(v) => setParam('conf', v)}>
          <option value="">Confidence: any</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
          <option value="uncertain">uncertain</option>
        </Select>
        <Select value={tagSource} onChange={(v) => setParam('source', v)}>
          <option value="both">Source: both</option>
          <option value="ai">AI only</option>
          <option value="human">Human only</option>
        </Select>
        {(q || contentType || reviewStatus || confidence || tagSource !== 'both') && (
          <button className="btn" onClick={clearAll}>
            <Filter className="w-3.5 h-3.5" /> Clear
          </button>
        )}
      </div>

      {isLoading && <div className="text-text-muted">Loading content…</div>}
      {error && <div className="text-conf-uncertain">Failed: {String(error)}</div>}
      {!isLoading && items.length === 0 && (
        <EmptyState
          title="No content mapped to this KP"
          hint="Try clearing filters, or no mappings exist for this KP yet."
        />
      )}

      {items.length > 0 && (
        <div className="card divide-y divide-line overflow-hidden">
          {items.map((m) => {
            const tag =
              m.ai_result?.proposed_tags?.find((t) => t.source_kp_id === kpId) ??
              m.human_tags?.find((t) => t.source_kp_id === kpId);
            const conf: ConfidenceLevel = (tag?.confidence ?? 'uncertain') as ConfidenceLevel;
            return (
              <Link
                key={m.content_id}
                to={`/content/${encodeURIComponent(m.content_id)}`}
                className="block p-4 hover:bg-bg-hover transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className="text-brand mt-0.5">{TYPE_ICON[m.content_type] ?? <FileText className="w-4 h-4" />}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-text truncate">{m.title}</span>
                      <span className="font-mono text-[11px] text-text-dim">{m.content_id.slice(0, 8)}</span>
                    </div>
                    <div className="text-xs text-text-muted mt-1 flex items-center gap-2 flex-wrap">
                      {m.topic_name && <span>{m.topic_name}</span>}
                      <span className="text-text-dim">·</span>
                      <span>{m.content_type}</span>
                      {tag?.tag_role && <span className="chip">role: {tag.tag_role}</span>}
                    </div>
                    {tag?.rationale && (
                      <p className="text-sm text-text-muted mt-2 line-clamp-2">{tag.rationale}</p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <ReviewStatusBadge status={m.review_status as ReviewStatus} />
                    <ConfidenceBadge level={conf} />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Select({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="input text-sm">
      {children}
    </select>
  );
}
