import { useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowDown10, Filter, Tag } from 'lucide-react';
import { fetchKpsWithCounts } from '../api/kps';
import SearchBox from '../components/SearchBox';
import EmptyState from '../components/EmptyState';
import CourseTabs from '../components/CourseTabs';
import { useDebounce } from '../hooks/useDebounce';
import type { KnowledgePointWithCounts, TagRole } from '../api/types';

const TAG_ROLES: TagRole[] = ['explain', 'practice', 'example', 'assessment', 'project', 'syntax', 'prerequisite'];
type SortMode = 'count_desc' | 'label_asc' | 'id_asc';

export default function KpListPage() {
  const { courseId = '' } = useParams();
  const [sp, setSp] = useSearchParams();
  const q = sp.get('q') ?? '';
  const hasMapped = sp.get('has_mapped') ?? '';
  const minCount = sp.get('min_count') ?? '';
  const roleFilter = (sp.get('role') ?? '') as TagRole | '';
  const sort = (sp.get('sort') ?? 'count_desc') as SortMode;
  const [localQ, setLocalQ] = useState(q);
  const debouncedQ = useDebounce(localQ, 300);

  // Sync debounced search to URL
  useMemo(() => {
    if (debouncedQ !== q) {
      const next = new URLSearchParams(sp);
      if (debouncedQ) next.set('q', debouncedQ);
      else next.delete('q');
      setSp(next, { replace: true });
    }
  }, [debouncedQ]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, error } = useQuery({
    queryKey: ['kps-counts', courseId],
    queryFn: () => fetchKpsWithCounts({ course_id: courseId, limit: 500 }),
  });

  const filtered = useMemo(() => {
    if (!data?.knowledge_points) return [] as KnowledgePointWithCounts[];
    const needle = debouncedQ.trim().toLowerCase();
    let rows = data.knowledge_points.filter((kp) => {
      if (needle) {
        const hay = [kp.source_kp_id, kp.label, kp.label_enum, kp.description].filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      if (hasMapped === 'yes' && kp.mapped_content_count === 0) return false;
      if (hasMapped === 'no' && kp.mapped_content_count > 0) return false;
      if (minCount) {
        const n = Number(minCount);
        if (!Number.isNaN(n) && kp.mapped_content_count < n) return false;
      }
      if (roleFilter) {
        const r = kp.tag_role_breakdown?.[roleFilter] ?? 0;
        if (r === 0) return false;
      }
      return true;
    });
    rows = rows.slice().sort((a, b) => {
      if (sort === 'label_asc') return a.label.localeCompare(b.label);
      if (sort === 'id_asc') return a.source_kp_id.localeCompare(b.source_kp_id);
      return b.mapped_content_count - a.mapped_content_count;
    });
    return rows;
  }, [data, debouncedQ, hasMapped, minCount, roleFilter, sort]);

  function setParam(key: string, val: string) {
    const next = new URLSearchParams(sp);
    if (val) next.set(key, val);
    else next.delete(key);
    setSp(next, { replace: true });
  }

  if (isLoading) return <div className="text-text-muted">Loading KPs…</div>;
  if (error) return <div className="text-conf-uncertain">Failed: {String(error)}</div>;

  return (
    <div>
      <CourseTabs />
      <div className="flex items-center gap-2 mb-4">
        <Tag className="w-5 h-5 text-brand" />
        <h1 className="text-xl font-semibold">Knowledge Points</h1>
        <span className="text-text-muted text-sm">
          {filtered.length} / {data?.count ?? 0}
        </span>
      </div>

      <div className="card p-3 mb-4 flex flex-wrap items-center gap-2">
        <SearchBox value={localQ} onChange={setLocalQ} placeholder="Search label, id, description…" />
        <Select value={hasMapped} onChange={(v) => setParam('has_mapped', v)} placeholder="Mapped?" >
          <option value="">Mapped: any</option>
          <option value="yes">Has mapped content</option>
          <option value="no">No mapped content</option>
        </Select>
        <Select value={minCount} onChange={(v) => setParam('min_count', v)}>
          <option value="">Min count: any</option>
          <option value="1">≥ 1</option>
          <option value="3">≥ 3</option>
          <option value="5">≥ 5</option>
          <option value="10">≥ 10</option>
        </Select>
        <Select value={roleFilter} onChange={(v) => setParam('role', v)}>
          <option value="">Tag role: any</option>
          {TAG_ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>
        <Select value={sort} onChange={(v) => setParam('sort', v)}>
          <option value="count_desc">Sort: most mapped</option>
          <option value="label_asc">Sort: label A→Z</option>
          <option value="id_asc">Sort: ID A→Z</option>
        </Select>
        {(q || hasMapped || minCount || roleFilter || sort !== 'count_desc') && (
          <button
            className="btn"
            onClick={() => {
              setLocalQ('');
              setSp(new URLSearchParams(), { replace: true });
            }}
          >
            <Filter className="w-3.5 h-3.5" /> Clear
          </button>
        )}
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No KPs match" hint="Adjust search or filters." />
      ) : (
        <div className="card divide-y divide-line overflow-hidden">
          {filtered.map((kp) => (
            <Link
              key={kp.source_kp_id}
              to={`/courses/${courseId}/kps/${encodeURIComponent(kp.source_kp_id)}${sp.toString() ? '' : ''}`}
              className="block p-4 hover:bg-bg-hover transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-text">{kp.label}</span>
                    <span className="font-mono text-xs text-text-dim">{kp.source_kp_id}</span>
                    {kp.label_enum && (
                      <span className="chip">{kp.label_enum}</span>
                    )}
                  </div>
                  {kp.description && (
                    <div className="text-sm text-text-muted mt-1.5 line-clamp-2">{kp.description}</div>
                  )}
                  {Object.keys(kp.tag_role_breakdown ?? {}).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {Object.entries(kp.tag_role_breakdown).map(([role, n]) => (
                        <span key={role} className="chip">
                          {role}: {n}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0 text-right">
                  <div>
                    <div className="text-2xl font-semibold tabular-nums text-text">
                      {kp.mapped_content_count}
                    </div>
                    <div className="text-xs text-text-dim flex items-center gap-1 justify-end">
                      <ArrowDown10 className="w-3 h-3" /> mapped
                    </div>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Select({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
  placeholder?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="input text-sm">
      {children}
    </select>
  );
}
