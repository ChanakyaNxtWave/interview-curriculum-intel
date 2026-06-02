import { Fragment, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowDown10, Building2, ChevronDown, ChevronRight, Filter, Layers, Tag } from 'lucide-react';
import { fetchKpsWithCounts } from '../api/kps';
import {
  fetchCourseGroupedQuestionMembers,
  fetchCourseGroupedQuestions,
} from '../api/courses';
import { fetchInterviewFacets } from '../api/interview';
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
  const groupedQ = sp.get('gq') ?? '';
  const groupedType = sp.get('gtype') ?? '';
  const groupedCompany = sp.get('gcompany') ?? '';
  const [localQ, setLocalQ] = useState(q);
  const [localGroupedQ, setLocalGroupedQ] = useState(groupedQ);
  const [expandedCanonicalId, setExpandedCanonicalId] = useState<number | null>(null);
  const debouncedQ = useDebounce(localQ, 300);
  const debouncedGroupedQ = useDebounce(localGroupedQ, 300);

  // Sync debounced search to URL
  useMemo(() => {
    if (debouncedQ !== q) {
      const next = new URLSearchParams(sp);
      if (debouncedQ) next.set('q', debouncedQ);
      else next.delete('q');
      setSp(next, { replace: true });
    }
  }, [debouncedQ]); // eslint-disable-line react-hooks/exhaustive-deps

  useMemo(() => {
    if (debouncedGroupedQ !== groupedQ) {
      const next = new URLSearchParams(sp);
      if (debouncedGroupedQ) next.set('gq', debouncedGroupedQ);
      else next.delete('gq');
      setSp(next, { replace: true });
    }
  }, [debouncedGroupedQ]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, error } = useQuery({
    queryKey: ['kps-counts', courseId],
    queryFn: () => fetchKpsWithCounts({ course_id: courseId, limit: 500 }),
  });
  const groupedQData = useQuery({
    queryKey: ['course-grouped-questions', courseId, debouncedGroupedQ, groupedType, groupedCompany],
    queryFn: () =>
      fetchCourseGroupedQuestions(courseId, {
        q: debouncedGroupedQ || undefined,
        question_type: groupedType || undefined,
        company_name: groupedCompany || undefined,
        limit: 200,
      }),
  });
  const facetsQ = useQuery({
    queryKey: ['interview-facets'],
    queryFn: fetchInterviewFacets,
  });
  const groupedMembersQ = useQuery({
    queryKey: ['course-grouped-question-members', courseId, expandedCanonicalId],
    queryFn: () =>
      fetchCourseGroupedQuestionMembers(courseId, expandedCanonicalId as number, 200, undefined, true),
    enabled: expandedCanonicalId != null,
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
    if (key === 'gq' || key === 'gtype' || key === 'gcompany') {
      setExpandedCanonicalId(null);
    }
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
        {(q ||
          hasMapped ||
          minCount ||
          roleFilter ||
          sort !== 'count_desc' ||
          groupedQ ||
          groupedType ||
          groupedCompany) && (
          <button
            className="btn"
            onClick={() => {
              setLocalQ('');
              setLocalGroupedQ('');
              setExpandedCanonicalId(null);
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

      <div className="mt-6">
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-5 h-5 text-brand" />
          <h2 className="text-lg font-semibold">Grouped Interview Questions</h2>
          <span className="text-text-muted text-sm">
            {groupedQData.data?.returned ?? 0} / {groupedQData.data?.total ?? 0}
          </span>
        </div>

        <div className="card p-3 mb-3 flex flex-wrap items-center gap-2">
          <SearchBox
            value={localGroupedQ}
            onChange={setLocalGroupedQ}
            placeholder="Search canonical or variant question..."
          />
          <Select value={groupedType} onChange={(v) => setParam('gtype', v)}>
            <option value="">Type: any</option>
            <option value="THEORY">THEORY</option>
            <option value="CODING">CODING</option>
          </Select>
          <Select value={groupedCompany} onChange={(v) => setParam('gcompany', v)}>
            <option value="">Company: any</option>
            {facetsQ.data?.companies?.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </div>

        {groupedQData.isLoading && (
          <div className="text-sm text-text-muted">Loading grouped interview questions…</div>
        )}
        {groupedQData.error && (
          <div className="text-conf-uncertain text-sm">Failed: {String(groupedQData.error)}</div>
        )}
        {!groupedQData.isLoading && !groupedQData.data?.items?.length && (
          <EmptyState
            title="No grouped questions yet"
            hint="Run sync and canonicalization to populate this table."
          />
        )}

        {!!groupedQData.data?.items?.length && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-bg-panel border-b border-line text-text-dim">
                <tr>
                  <th className="text-left px-3 py-2 w-8" />
                  <th className="text-left px-3 py-2">Canonical Question</th>
                  <th className="text-left px-3 py-2">Type</th>
                  <th className="text-left px-3 py-2">Members</th>
                  <th className="text-left px-3 py-2">Companies</th>
                  <th className="text-left px-3 py-2">Repeat Ignore Count</th>
                </tr>
              </thead>
              <tbody>
                {groupedQData.data.items.map((item) => {
                  const open = expandedCanonicalId === item.canonical_id;
                  const showMembers =
                    open &&
                    groupedMembersQ.data?.canonical_id === item.canonical_id &&
                    groupedMembersQ.data?.members;
                  return (
                    <Fragment key={`canon-${item.canonical_id}`}>
                      <tr className="border-b border-line/60">
                        <td className="px-3 py-2 align-top">
                          <button
                            className="text-text-dim hover:text-brand"
                            onClick={() =>
                              setExpandedCanonicalId((prev) =>
                                prev === item.canonical_id ? null : item.canonical_id,
                              )
                            }
                            title={open ? 'Collapse variants' : 'Expand variants'}
                          >
                            {open ? (
                              <ChevronDown className="w-4 h-4" />
                            ) : (
                              <ChevronRight className="w-4 h-4" />
                            )}
                          </button>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <div className="font-medium text-text">{item.canonical_question}</div>
                          <div className="text-xs text-text-dim font-mono">{item.canonical_slug}</div>
                        </td>
                        <td className="px-3 py-2 align-top">{item.question_type || '—'}</td>
                        <td className="px-3 py-2 align-top">{item.member_count}</td>
                        <td className="px-3 py-2 align-top">{item.company_count}</td>
                        <td className="px-3 py-2 align-top">
                          {item.repeated_within_company_count}
                        </td>
                      </tr>
                      {open && (
                        <tr className="border-b border-line/40 bg-bg-panel/30">
                          <td />
                          <td colSpan={5} className="px-3 py-3">
                            {groupedMembersQ.isLoading && (
                              <div className="text-xs text-text-muted">Loading variants…</div>
                            )}
                            {showMembers && (
                              <div className="space-y-2 max-h-64 overflow-auto">
                                {showMembers.map((m) => (
                                  <div
                                    key={m.row_key}
                                    className="text-xs border border-line rounded-md p-2 bg-bg-panel"
                                  >
                                    <div className="text-text">{m.question}</div>
                                    <div className="text-text-dim mt-1 flex items-center gap-2 flex-wrap">
                                      {m.company_name && (
                                        <span className="chip">
                                          <Building2 className="w-3 h-3" /> {m.company_name}
                                        </span>
                                      )}
                                      {m.role && <span className="chip">{m.role}</span>}
                                      {m.interview_date && <span className="chip">{m.interview_date}</span>}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
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
