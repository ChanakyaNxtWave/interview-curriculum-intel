import { useMemo, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Sparkles, Filter, MessagesSquare, ChevronDown, ChevronRight } from 'lucide-react';
import { fetchTheoryQuestions } from '../api/theory';
import { fetchCodingQuestions } from '../api/coding';
import SearchBox from '../components/SearchBox';
import EmptyState from '../components/EmptyState';
import DateRangeFilter, { type DurationPreset } from '../components/DateRangeFilter';
import VerdictBadge from '../components/VerdictBadge';
import { effectiveVerdict } from '../lib/verdict';
import ConfidenceBar from '../components/ConfidenceBar';
import ReviewStatusBadge from '../components/ReviewStatusBadge';
import CourseTabs from '../components/CourseTabs';
import SimilarQuestionsPanel from '../components/SimilarQuestionsPanel';
import ListSkeleton from '../components/ListSkeleton';
import { InlineSpinner } from '../components/BusyOverlay';
import { useDebounce } from '../hooks/useDebounce';
import type { ReviewStatus } from '../api/types';

export default function TheoryQuestionsPage() {
  const { courseId = '' } = useParams();
  const location = useLocation();
  const isCodingRoute = location.pathname.includes('/coding-questions');
  const [sp, setSp] = useSearchParams();
  const q = sp.get('q') ?? '';
  const verdict = sp.get('verdict') ?? '';
  const status = sp.get('status') ?? '';
  const duration = (sp.get('duration') ?? '') as DurationPreset;
  const dateFrom = sp.get('from') ?? '';
  const dateTo = sp.get('to') ?? '';
  const [localQ, setLocalQ] = useState(q);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const debouncedQ = useDebounce(localQ, 300);

  useMemo(() => {
    if (debouncedQ !== q) {
      const next = new URLSearchParams(sp);
      if (debouncedQ) next.set('q', debouncedQ);
      else next.delete('q');
      setSp(next, { replace: true });
    }
  }, [debouncedQ]); // eslint-disable-line react-hooks/exhaustive-deps

  const listQ = useQuery({
    queryKey: [
      isCodingRoute ? 'coding-list' : 'theory-list',
      debouncedQ,
      verdict,
      status,
      duration,
      dateFrom,
      dateTo,
    ],
    queryFn: () =>
      (isCodingRoute ? fetchCodingQuestions : fetchTheoryQuestions)({
        q: debouncedQ || undefined,
        verdict: verdict || undefined,
        review_status: status || undefined,
        duration: duration && duration !== 'custom' ? duration : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        unique: true,
        limit: 500,
      }),
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

  const items = listQ.data?.items ?? [];
  const stats = listQ.data?.stats;
  const applied = listQ.data?.applied_date_range;

  return (
    <div>
      <CourseTabs />
      <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-brand" />
          <h1 className="text-xl font-semibold">
            {isCodingRoute ? 'Coding Questions' : 'Theory Questions'}
          </h1>
          <span className="text-text-muted text-sm">{items.length}</span>
        </div>
        {stats && (
          <span className="text-xs text-text-muted">
            {Object.entries(stats.by_status)
              .map(([k, n]) => `${k}: ${n}`)
              .join(' · ')}
          </span>
        )}
      </div>

      <VerdictTabs
        current={verdict}
        counts={stats?.by_verdict}
        onChange={(v) => setParam('verdict', v)}
      />

      <div className="card p-3 mb-3">
        <DateRangeFilter
          value={{ duration, from: dateFrom, to: dateTo }}
          onChange={setDateRange}
        />
        {applied && (applied.date_from || applied.date_to) && (
          <div className="mt-2 text-xs text-text-dim">
            {applied.date_from ?? '…'} → {applied.date_to ?? '…'}
          </div>
        )}
      </div>

      <div className="card p-3 mb-4 flex flex-wrap items-center gap-2">
        <SearchBox
          value={localQ}
          onChange={setLocalQ}
          placeholder="Search question text or rationale…"
        />
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
          value={status}
          onChange={(e) => setParam('status', e.target.value)}
          className="input text-sm"
        >
          <option value="">Status: any</option>
          <option value="pending">pending</option>
          <option value="needs_review">needs review</option>
          <option value="approved">approved</option>
          <option value="rejected">rejected</option>
        </select>
        {(q || verdict || status || duration || dateFrom || dateTo) && (
          <button className="btn" onClick={clearAll}>
            <Filter className="w-3.5 h-3.5" /> Clear
          </button>
        )}
      </div>

      {listQ.isLoading && <ListSkeleton rows={6} />}
      {listQ.isFetching && !listQ.isLoading && (
        <div className="mb-2"><InlineSpinner label="Refreshing…" /></div>
      )}
      {listQ.error && <div className="text-conf-uncertain">Failed: {String(listQ.error)}</div>}
      {!listQ.isLoading && items.length === 0 && (
        <EmptyState
          title="No question tags yet"
          hint={
            isCodingRoute
              ? "Run tagging from Interview Questions (CODING) or use Tag pending."
              : "Run tagging from Interview Questions (THEORY) or use Tag pending."
          }
        />
      )}

      {items.length > 0 && (
        <div className="card divide-y divide-line overflow-hidden">
          {items.map((t) => {
            const expandId =
              t.canonical_id != null
                ? `c:${t.canonical_id}`
                : t.group_key
                ? `g:${t.group_key}`
                : t.row_key;
            const similarCount = t.similar_count ?? 0;
            const isExpanded = expandedKey === expandId;
            const displayQuestion =
              t.canonical_question || t.group_canonical_question || t.question_text;

            return (
              <div key={expandId} className="hover:bg-bg-hover/50 transition-colors">
                <Link
                  to={`/courses/${courseId}/theory-questions/${encodeURIComponent(t.row_key)}${
                    isCodingRoute ? '?type=coding' : ''
                  }`}
                  className="block p-4"
                >
                  <div className="flex items-start gap-3">
                    <MessagesSquare className="w-4 h-4 text-brand mt-1 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-text leading-snug line-clamp-2">{displayQuestion}</p>
                      {displayQuestion !== t.question_text && (
                        <p className="text-xs text-text-dim mt-1 line-clamp-1">
                          Tagged as: {t.question_text}
                        </p>
                      )}
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-text-muted">
                        {t.interview?.company_name && (
                          <span className="chip">{t.interview.company_name}</span>
                        )}
                        {t.interview?.role && (
                          <span
                            className="chip max-w-[200px] truncate"
                            title={t.interview.role}
                          >
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
                        {t.canonical_slug && (
                          <span className="chip font-mono">{t.canonical_slug}</span>
                        )}
                        {(t.related_tag_count ?? 1) > 1 && (
                          <span className="chip">{t.related_tag_count} tag variants</span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0 min-w-[180px]">
                      <VerdictBadge verdict={effectiveVerdict(t)} />
                      <ConfidenceBar value={t.overall_confidence} />
                      <ReviewStatusBadge status={t.review_status as ReviewStatus} />
                    </div>
                  </div>
                </Link>
                {similarCount > 0 && (
                  <div className="px-4 pb-3">
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedKey(isExpanded ? null : expandId)
                      }
                      className="inline-flex items-center gap-1.5 text-xs text-brand hover:text-brand/80 pl-7"
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" />
                      )}
                      {similarCount} similar question{similarCount === 1 ? '' : 's'}
                    </button>
                  </div>
                )}
                {isExpanded && similarCount > 0 && t.canonical_id != null && (
                  <SimilarQuestionsPanel
                    courseId={courseId}
                    canonicalId={t.canonical_id}
                    representativeRowKey={t.row_key}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function VerdictTabs({
  current,
  counts,
  onChange,
}: {
  current: string;
  counts?: Record<string, number>;
  onChange: (v: string) => void;
}) {
  const tabs: { value: string; label: string; cls: string }[] = [
    { value: '', label: 'All', cls: '' },
    { value: 'covered', label: 'Covered', cls: 'text-conf-high' },
    { value: 'not_covered', label: 'Not Covered', cls: 'text-conf-uncertain' },
  ];
  const totalAll = counts
    ? Object.values(counts).reduce((a, b) => a + b, 0)
    : 0;
  return (
    <nav className="card p-1 mb-3 inline-flex flex-wrap gap-1">
      {tabs.map((t) => {
        const isActive = current === t.value;
        const count =
          t.value === ''
            ? totalAll
            : counts
            ? t.value === 'not_covered'
              ? (counts.not_covered ?? 0) +
                (counts.partially_covered ?? 0) +
                (counts.uncertain ?? 0)
              : counts[t.value] ?? 0
            : 0;
        return (
          <button
            key={t.value}
            onClick={() => onChange(t.value)}
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-sm border ${
              isActive
                ? 'bg-brand/15 border-brand/40 text-brand'
                : `border-transparent ${t.cls} hover:bg-bg-hover`
            }`}
          >
            {t.label}
            {count > 0 && (
              <span
                className={`text-[10px] tabular-nums px-1.5 py-0.5 rounded-full ${
                  isActive ? 'bg-brand/20' : 'bg-bg-panel border border-line'
                }`}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
