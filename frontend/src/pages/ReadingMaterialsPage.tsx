import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import {
  BookOpen,
  FolderGit2,
  FileText,
  Filter,
  Loader2,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import CourseTabs from '../components/CourseTabs';
import StickyPageChrome from '../components/StickyPageChrome';
import SearchBox from '../components/SearchBox';
import EmptyState from '../components/EmptyState';
import ListSkeleton from '../components/ListSkeleton';
import { useDebounce } from '../hooks/useDebounce';
import { fetchMappings, fetchFacets } from '../api/mappings';
import { fetchContentBody } from '../api/mappings';

export default function ReadingMaterialsPage() {
  const location = useLocation();
  const isProjectsRoute = location.pathname.includes('/projects');
  const contentType = isProjectsRoute ? 'project' : 'reading_material';
  const [q, setQ] = useState('');
  const [topic, setTopic] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const debouncedQ = useDebounce(q, 300);

  const facetsQ = useQuery({
    queryKey: ['mappings-facets'],
    queryFn: fetchFacets,
  });

  const listQ = useQuery({
    queryKey: [isProjectsRoute ? 'projects' : 'reading-materials', debouncedQ, topic],
    queryFn: () =>
      fetchMappings({
        content_type: contentType,
        q: debouncedQ || undefined,
        topic_name: topic || undefined,
        limit: 1000,
      }),
  });

  const items = listQ.data?.items ?? [];
  const facets = facetsQ.data;

  // Sort topics + dedupe titles for cleaner list (one row per content_id)
  const byTopic = useMemo(() => {
    const groups: Record<string, typeof items> = {};
    for (const m of items) {
      const t = m.topic_name || 'Untitled topic';
      (groups[t] ||= []).push(m);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [items]);

  return (
    <div>
      <StickyPageChrome>
        <CourseTabs />

        <div className="flex items-center gap-2">
          {isProjectsRoute ? (
            <FolderGit2 className="w-5 h-5 text-brand" />
          ) : (
            <BookOpen className="w-5 h-5 text-brand" />
          )}
          <h1 className="text-xl font-semibold">
            {isProjectsRoute ? 'Projects' : 'Reading Materials'}
          </h1>
          <span className="text-text-muted text-sm">{items.length}</span>
        </div>

        <div className="card p-3 flex flex-wrap items-center gap-2">
          <SearchBox
            value={q}
            onChange={setQ}
            placeholder={isProjectsRoute ? 'Search project title or topic…' : 'Search title or topic…'}
          />
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="input text-sm max-w-[260px]"
          >
            <option value="">Topic: all</option>
            {facets?.topics.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          {(q || topic) && (
            <button
              className="btn"
              onClick={() => {
                setQ('');
                setTopic('');
              }}
            >
              <Filter className="w-3.5 h-3.5" /> Clear
            </button>
          )}
        </div>
      </StickyPageChrome>

      {listQ.isLoading && <ListSkeleton rows={6} />}
      {listQ.error && (
        <div className="text-conf-uncertain">Failed: {String(listQ.error)}</div>
      )}
      {!listQ.isLoading && items.length === 0 && (
        <EmptyState
          title={isProjectsRoute ? 'No projects found' : 'No reading materials'}
          hint="Try clearing filters."
        />
      )}

      {items.length > 0 && (
        <div className="space-y-4">
          {byTopic.map(([topicName, group]) => (
            <div key={topicName} className="card overflow-hidden">
              <div className="px-4 py-2 bg-bg-panel border-b border-line text-xs uppercase tracking-wide text-text-dim">
                {topicName} · {group.length}
              </div>
              <div className="divide-y divide-line">
                {group.map((m) => (
                  <button
                    key={m.content_id}
                    onClick={() => setSelectedId(m.content_id)}
                    className="w-full text-left p-3 hover:bg-bg-hover transition-colors flex items-start gap-3"
                  >
                    <FileText className="w-4 h-4 text-brand mt-0.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-text font-medium truncate">{m.title}</div>
                      <div className="text-xs text-text-dim mt-0.5">
                        {(m.ai_result?.proposed_tags?.length ?? 0) +
                          (m.human_tags?.length ?? 0)}{' '}
                        KP tags · {m.review_status}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedId && (
        <ReadingMaterialModal contentId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

function ReadingMaterialModal({
  contentId,
  onClose,
}: {
  contentId: string;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['content-body', contentId],
    queryFn: () => fetchContentBody(contentId),
  });

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="card max-w-4xl w-full max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-line">
          <div className="min-w-0">
            <h3 className="font-semibold text-text truncate">{data?.title ?? 'Loading…'}</h3>
            <div className="text-xs text-text-dim mt-0.5 flex items-center gap-2 flex-wrap">
              {data?.topic_name && <span className="chip">{data.topic_name}</span>}
              {data?.content_type && <span className="chip">{data.content_type}</span>}
              <span className="font-mono text-text-dim">{contentId.slice(0, 12)}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-text-dim hover:text-text"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto p-5 flex-1">
          {isLoading && (
            <div className="flex items-center gap-2 text-text-muted text-sm">
              <Loader2 className="w-4 h-4 animate-spin text-brand" /> Loading content…
            </div>
          )}
          {error && (
            <div className="text-conf-uncertain text-sm">{String(error)}</div>
          )}
          {data && (
            <article className="prose prose-invert max-w-none reading-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {data.body_text || '_No body text._'}
              </ReactMarkdown>
            </article>
          )}
        </div>
      </div>
    </div>
  );
}
