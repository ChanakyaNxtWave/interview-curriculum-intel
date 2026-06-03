import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Inbox, Filter, MessagesSquare, ChevronRight } from 'lucide-react';
import { fetchTheoryQuestions } from '../api/theory';
import { fetchCodingQuestions } from '../api/coding';
import SearchBox from '../components/SearchBox';
import EmptyState from '../components/EmptyState';
import VerdictBadge from '../components/VerdictBadge';
import { effectiveVerdict } from '../lib/verdict';
import ConfidenceBar from '../components/ConfidenceBar';
import ReviewStatusBadge from '../components/ReviewStatusBadge';
import DateRangeFilter, { type DurationPreset } from '../components/DateRangeFilter';
import AskedChip from '../components/AskedChip';
import GroupMembersModal from '../components/GroupMembersModal';
import ListSkeleton from '../components/ListSkeleton';
import { InlineSpinner } from '../components/BusyOverlay';
import { useDebounce } from '../hooks/useDebounce';
import StickyPageChrome from '../components/StickyPageChrome';
import type { ReviewStatus, TheoryTag } from '../api/types';

// Pilot: all theory rows belong to Programming Foundations.
// When multi-course lands, derive courseId from the tag row.
const COURSE_ID = 'programming_foundations';

const FILTER_PRESETS: { value: string; label: string; statusFilter?: string }[] = [
  { value: 'open', label: 'Open (pending + needs review)' },
  { value: 'needs_review', label: 'Needs review only', statusFilter: 'needs_review' },
  { value: 'pending', label: 'Pending only', statusFilter: 'pending' },
  { value: 'rejected', label: 'Rejected only', statusFilter: 'rejected' },
  { value: 'all', label: 'All statuses' },
];

export default function ReviewQueuePage() {
  const [sp, setSp] = useSearchParams();
  const preset = sp.get('preset') ?? 'open';
  const verdict = sp.get('verdict') ?? '';
  const q = sp.get('q') ?? '';
  const duration = (sp.get('duration') ?? '') as DurationPreset;
  const dateFrom = sp.get('from') ?? '';
  const dateTo = sp.get('to') ?? '';
  const sort = sp.get('sort') ?? 'conf_asc';
  const [localQ, setLocalQ] = useState(q);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const debouncedQ = useDebounce(localQ, 300);

  useMemo(() => {
    if (debouncedQ !== q) {
      const next = new URLSearchParams(sp);
      if (debouncedQ) next.set('q', debouncedQ);
      else next.delete('q');
      setSp(next, { replace: true });
    }
  }, [debouncedQ]); // eslint-disable-line react-hooks/exhaustive-deps

  const presetDef = FILTER_PRESETS.find((p) => p.value === preset) ?? FILTER_PRESETS[0];

  // Fetch with optional server-side review_status filter; client-side filter for 'open'.
  // THEORY and CODING tags live in separate tables/namespaces — fetch both and merge.
  const listQ = useQuery({
    queryKey: ['review-queue', preset, verdict, debouncedQ, duration, dateFrom, dateTo],
    queryFn: async () => {
      const filters = {
        review_status: presetDef.statusFilter,
        verdict: verdict || undefined,
        q: debouncedQ || undefined,
        duration: duration && duration !== 'custom' ? duration : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: 1000,
      };
      const [theory, coding] = await Promise.all([
        fetchTheoryQuestions(filters),
        fetchCodingQuestions(filters),
      ]);
      const mergeCount = (a: Record<string, number> = {}, b: Record<string, number> = {}) => {
        const out: Record<string, number> = { ...a };
        for (const [k, v] of Object.entries(b)) out[k] = (out[k] ?? 0) + v;
        return out;
      };
      return {
        items: [...(theory.items ?? []), ...(coding.items ?? [])],
        stats: {
          by_status: mergeCount(theory.stats?.by_status, coding.stats?.by_status),
          by_verdict: mergeCount(theory.stats?.by_verdict, coding.stats?.by_verdict),
        },
      };
    },
  });

  function setParam(key: string, val: string) {
    const next = new URLSearchParams(sp);
    if (val) next.set(key, val);
    else next.delete(key);
    setSp(next, { replace: true });
  }
  function setDateRange(v: { duration: DurationPreset; from: string; to: string }) {
    const next = new URLSearchParams(sp);
    if (v.duration) next.set('duration', v.duration);
    else next.delete('duration');
    if (v.from) next.set('from', v.from);
    else next.delete('from');
    if (v.to) next.set('to', v.to);
    else next.delete('to');
    setSp(next, { replace: true });
  }
  function clearAll() {
    setLocalQ('');
    setSp(new URLSearchParams(), { replace: true });
  }

  const raw = listQ.data?.items ?? [];
  const items: TheoryTag[] = useMemo(() => {
    let rows = raw;
    if (preset === 'open') {
      rows = rows.filter((r) => r.review_status === 'pending' || r.review_status === 'needs_review');
    }
    rows = rows.slice().sort((a, b) => {
      if (sort === 'conf_asc') return a.overall_confidence - b.overall_confidence;
      if (sort === 'conf_desc') return b.overall_confidence - a.overall_confidence;
      if (sort === 'updated_desc')
        return (b.updated_at ?? '').localeCompare(a.updated_at ?? '');
      return 0;
    });
    return rows;
  }, [raw, preset, sort]);

  const stats = listQ.data?.stats;
  const openCount =
    (stats?.by_status?.pending ?? 0) + (stats?.by_status?.needs_review ?? 0);

  return (
    <div>
      <StickyPageChrome>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Inbox className="w-5 h-5 text-brand" />
            <h1 className="text-xl font-semibold">Review Queue</h1>
            <span className="text-text-muted text-sm">
              {items.length} shown
              {openCount > 0 && (
                <span className="ml-2 chip-on">{openCount} open</span>
              )}
            </span>
          </div>
          {stats && (
            <div className="text-xs text-text-muted flex flex-wrap gap-2">
              {Object.entries(stats.by_status).map(([k, n]) => (
                <span key={k} className="chip">
                  {k}: {n}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="card p-3">
          <DateRangeFilter
            value={{ duration, from: dateFrom, to: dateTo }}
            onChange={setDateRange}
          />
        </div>

        <div className="card p-3 flex flex-wrap items-center gap-2">
        <SearchBox
          value={localQ}
          onChange={setLocalQ}
          placeholder="Search question text or rationale…"
        />
        <select
          value={preset}
          onChange={(e) => setParam('preset', e.target.value)}
          className="input text-sm"
        >
          {FILTER_PRESETS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <select
          value={verdict}
          onChange={(e) => setParam('verdict', e.target.value)}
          className="input text-sm"
        >
          <option value="">Verdict: any</option>
          <option value="covered">covered</option>
          <option value="not_covered">not_covered</option>
        </select>
        <select
          value={sort}
          onChange={(e) => setParam('sort', e.target.value)}
          className="input text-sm"
        >
          <option value="conf_asc">Sort: lowest conf first</option>
          <option value="conf_desc">Sort: highest conf first</option>
          <option value="updated_desc">Sort: recently updated</option>
        </select>
        {(q || preset !== 'open' || verdict || duration || dateFrom || dateTo || sort !== 'conf_asc') && (
          <button className="btn" onClick={clearAll}>
            <Filter className="w-3.5 h-3.5" /> Clear
          </button>
        )}
        </div>
      </StickyPageChrome>

      {listQ.isLoading && <ListSkeleton rows={6} />}
      {listQ.isFetching && !listQ.isLoading && (
        <div className="mb-2"><InlineSpinner label="Refreshing…" /></div>
      )}
      {listQ.error && <div className="text-conf-uncertain">Failed: {String(listQ.error)}</div>}
      {!listQ.isLoading && items.length === 0 && (
        <EmptyState
          title="Nothing to review"
          hint="All tagged questions in this slice have been reviewed."
        />
      )}

      {items.length > 0 && (
        <div className="card divide-y divide-line overflow-hidden">
          {items.map((t) => (
            <Link
              key={t.row_key}
              to={`/courses/${COURSE_ID}/theory-questions/${encodeURIComponent(t.row_key)}${
                (t.question_type || '').toUpperCase() === 'CODING' ? '?type=coding' : ''
              }`}
              className="block p-4 hover:bg-bg-hover transition-colors"
            >
              <div className="flex items-start gap-3">
                <MessagesSquare className="w-4 h-4 text-brand mt-1 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-text leading-snug line-clamp-2">{t.question_text}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-text-muted">
                    {t.interview?.company_name && (
                      <span className="chip">{t.interview.company_name}</span>
                    )}
                    {t.interview?.role && (
                      <span className="chip max-w-[200px] truncate" title={t.interview.role}>
                        {t.interview.role}
                      </span>
                    )}
                    {t.interview?.interview_date && (
                      <span className="chip">{t.interview.interview_date}</span>
                    )}
                    {t.required_kps?.length > 0 && (
                      <span className="chip">{t.required_kps.length} KPs</span>
                    )}
                    {t.citations?.length > 0 && (
                      <span className="chip">{t.citations.length} citations</span>
                    )}
                    {t.review_reasons?.length > 0 && (
                      <span className="chip text-status-needs border-status-needs/40 bg-status-needs/10">
                        {t.review_reasons[0].slice(0, 60)}
                      </span>
                    )}
                    {t.group_key && (
                      <AskedChip
                        count={t.group_member_count}
                        onClick={() => setOpenGroup(t.group_key as string)}
                      />
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0 min-w-[180px]">
                  <VerdictBadge verdict={effectiveVerdict(t)} />
                  <ConfidenceBar value={t.overall_confidence} />
                  <ReviewStatusBadge status={t.review_status as ReviewStatus} />
                </div>
                <ChevronRight className="w-4 h-4 text-text-dim mt-1 shrink-0" />
              </div>
            </Link>
          ))}
        </div>
      )}

      {openGroup && (
        <GroupMembersModal groupKey={openGroup} onClose={() => setOpenGroup(null)} />
      )}
    </div>
  );
}
