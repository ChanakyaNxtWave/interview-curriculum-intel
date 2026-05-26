import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, FileText, Code2, FolderGit2, ExternalLink } from 'lucide-react';
import { fetchMapping } from '../api/mappings';
import ConfidenceBadge from '../components/ConfidenceBadge';
import ReviewStatusBadge from '../components/ReviewStatusBadge';
import type { ConfidenceLevel, ReviewStatus, ProposedTag } from '../api/types';

const TYPE_ICON: Record<string, React.ReactNode> = {
  reading_material: <FileText className="w-4 h-4" />,
  coding_question: <Code2 className="w-4 h-4" />,
  project: <FolderGit2 className="w-4 h-4" />,
};

export default function ContentDetailPage() {
  const { contentId = '' } = useParams();
  const { data, isLoading, error } = useQuery({
    queryKey: ['mapping', contentId],
    queryFn: () => fetchMapping(contentId),
  });

  if (isLoading) return <div className="text-text-muted">Loading…</div>;
  if (error) return <div className="text-conf-uncertain">Failed: {String(error)}</div>;
  if (!data) return <div className="text-text-muted">Not found.</div>;

  const aiTags = data.ai_result?.proposed_tags ?? [];
  const humanTags = data.human_tags ?? [];

  return (
    <div>
      <div className="mb-4">
        <Link to="/" onClick={(e) => { e.preventDefault(); history.back(); }} className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text">
          <ArrowLeft className="w-4 h-4" /> Back
        </Link>
      </div>

      <div className="card p-5 mb-4">
        <div className="flex items-start gap-3 flex-wrap">
          <div className="text-brand mt-1">{TYPE_ICON[data.content_type] ?? <FileText className="w-5 h-5" />}</div>
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold text-text">{data.title}</h1>
            <div className="text-xs text-text-dim mt-1 flex items-center gap-2 flex-wrap">
              <span className="font-mono">{data.content_id}</span>
              <span>·</span>
              <span>{data.content_type}</span>
              {data.topic_name && <><span>·</span><span>{data.topic_name}</span></>}
              {data.course_title && <><span>·</span><span>{data.course_title}</span></>}
            </div>
            {data.file_path && (
              <div className="text-xs text-text-dim mt-2 font-mono inline-flex items-center gap-1">
                <ExternalLink className="w-3 h-3" />
                {data.file_path}
              </div>
            )}
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <ReviewStatusBadge status={data.review_status as ReviewStatus} />
            {data.ai_result?.overall_confidence && (
              <ConfidenceBadge level={data.ai_result.overall_confidence as ConfidenceLevel} />
            )}
          </div>
        </div>

        {data.ai_result?.review_reasons && data.ai_result.review_reasons.length > 0 && (
          <div className="mt-4 p-3 rounded-md border border-status-needs/40 bg-status-needs/10">
            <div className="text-xs font-semibold text-status-needs uppercase tracking-wide mb-1">
              Flagged for review
            </div>
            <ul className="text-sm text-text-muted list-disc list-inside space-y-0.5">
              {data.ai_result.review_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {data.reviewer_notes && (
          <div className="mt-3 p-3 rounded-md bg-bg-panel border border-line">
            <div className="text-xs text-text-dim mb-1">Reviewer notes</div>
            <div className="text-sm text-text whitespace-pre-wrap">{data.reviewer_notes}</div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TagSection title="AI tags" tags={aiTags} empty="No AI tags yet." />
        <TagSection title="Human tags" tags={humanTags} empty="No human overrides." />
      </div>
    </div>
  );
}

function TagSection({ title, tags, empty }: { title: string; tags: ProposedTag[]; empty: string }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-text">{title}</h2>
        <span className="text-xs text-text-dim">{tags.length}</span>
      </div>
      {tags.length === 0 ? (
        <div className="text-sm text-text-muted">{empty}</div>
      ) : (
        <div className="space-y-3">
          {tags.map((t, i) => (
            <div key={`${t.source_kp_id}-${i}`} className="rounded-md border border-line p-3 bg-bg-panel">
              <div className="flex items-start gap-2 flex-wrap">
                <Link
                  to={`/content/lookup/kp/${encodeURIComponent(t.source_kp_id)}`}
                  className="font-mono text-xs text-brand hover:underline"
                  onClick={(e) => e.preventDefault()}
                  title="KP id"
                >
                  {t.source_kp_id}
                </Link>
                <span className="text-sm text-text font-medium flex-1 min-w-0">{t.label ?? ''}</span>
                <ConfidenceBadge level={(t.confidence ?? 'uncertain') as ConfidenceLevel} />
              </div>
              <div className="flex items-center gap-2 mt-1.5 text-xs text-text-dim">
                <span className="chip">role: {t.tag_role}</span>
              </div>
              {t.rationale && (
                <p className="text-sm text-text-muted mt-2 leading-relaxed">{t.rationale}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
