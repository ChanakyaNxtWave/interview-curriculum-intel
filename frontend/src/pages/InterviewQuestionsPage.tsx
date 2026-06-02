import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Filter,
  MessagesSquare,
  RefreshCw,
  Building2,
  Briefcase,
  Code2,
  Calendar,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Clock,
} from 'lucide-react';
import {
  fetchInterviewFacets,
  fetchInterviewQuestions,
  fetchInterviewSyncStatus,
  fetchNormalizeStatus,
  triggerInterviewSync,
  triggerNormalize,
  deleteInterviewQuestion,
} from '../api/interview';
import { fetchPendingCount, tagBatch, tagPending, tagTheoryQuestion } from '../api/theory';
import {
  fetchCodingPendingCount,
  tagCodingBatch,
  tagCodingPending,
  tagCodingQuestion,
} from '../api/coding';
import { CheckSquare, Layers, Loader2, Rows, Sparkles, Square, Tag, Wand2 } from 'lucide-react';
import VerdictBadge from '../components/VerdictBadge';
import ConfidenceBar from '../components/ConfidenceBar';
import SearchBox from '../components/SearchBox';
import EmptyState from '../components/EmptyState';
import DateRangeFilter, { type DurationPreset } from '../components/DateRangeFilter';
import AskedChip from '../components/AskedChip';
import GroupMembersModal from '../components/GroupMembersModal';
import ListSkeleton from '../components/ListSkeleton';
import { InlineSpinner } from '../components/BusyOverlay';
import TagProgressModal from '../components/TagProgressModal';
import { useDebounce } from '../hooks/useDebounce';

export default function InterviewQuestionsPage() {
  const qc = useQueryClient();
  const [sp, setSp] = useSearchParams();
  const q = sp.get('q') ?? '';
  const company = sp.get('company') ?? '';
  const role = sp.get('role') ?? '';
  const qtype = sp.get('type') ?? '';
  const tech = sp.get('tech') ?? '';
  const product = sp.get('product') ?? '';
  const stage = sp.get('stage') ?? '';
  const duration = (sp.get('duration') ?? '') as DurationPreset;
  const dateFrom = sp.get('from') ?? '';
  const dateTo = sp.get('to') ?? '';
  const grouped = sp.get('view') !== 'flat'; // default grouped
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

  const facetsQ = useQuery({
    queryKey: ['interview-facets'],
    queryFn: fetchInterviewFacets,
  });

  const statusQ = useQuery({
    queryKey: ['interview-sync-status'],
    queryFn: fetchInterviewSyncStatus,
    refetchInterval: 30_000,
  });

  const listQ = useQuery({
    queryKey: [
      'interview-list',
      debouncedQ,
      company,
      role,
      qtype,
      tech,
      product,
      duration,
      dateFrom,
      dateTo,
      grouped,
    ],
    queryFn: () =>
      fetchInterviewQuestions({
        q: debouncedQ || undefined,
        company_name: company || undefined,
        role: role || undefined,
        question_type: qtype || undefined,
        tech_stack: tech || undefined,
        product: product || undefined,
        duration: duration && duration !== 'custom' ? duration : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        group_by: grouped,
        limit: 1000,
      }),
  });

  const normalizeStatusQ = useQuery({
    queryKey: ['normalize-status'],
    queryFn: fetchNormalizeStatus,
    refetchInterval: 10_000,
  });

  const normalizeMutation = useMutation({
    mutationFn: () => triggerNormalize(100),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['interview-list'] });
      qc.invalidateQueries({ queryKey: ['normalize-status'] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: triggerInterviewSync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['interview-list'] });
      qc.invalidateQueries({ queryKey: ['interview-facets'] });
      qc.invalidateQueries({ queryKey: ['interview-sync-status'] });
      qc.invalidateQueries({ queryKey: ['theory-list'] });
      qc.invalidateQueries({ queryKey: ['review-queue'] });
      qc.invalidateQueries({ queryKey: ['review-count'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (rowKey: string) => deleteInterviewQuestion(rowKey),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['interview-list'] });
      qc.invalidateQueries({ queryKey: ['interview-facets'] });
      qc.invalidateQueries({ queryKey: ['theory-list'] });
      qc.invalidateQueries({ queryKey: ['review-queue'] });
      qc.invalidateQueries({ queryKey: ['review-count'] });
      qc.invalidateQueries({ queryKey: ['theory-pending-count'] });
      qc.invalidateQueries({ queryKey: ['coding-pending-count'] });
    },
  });

  const pendingCountQ = useQuery({
    queryKey: ['theory-pending-count'],
    queryFn: fetchPendingCount,
    refetchInterval: 10_000,
  });

  const codingPendingCountQ = useQuery({
    queryKey: ['coding-pending-count'],
    queryFn: fetchCodingPendingCount,
    refetchInterval: 10_000,
  });

  function invalidateTagging() {
    qc.invalidateQueries({ queryKey: ['theory-list'] });
    qc.invalidateQueries({ queryKey: ['review-queue'] });
    qc.invalidateQueries({ queryKey: ['review-count'] });
    qc.invalidateQueries({ queryKey: ['interview-list'] });
    qc.invalidateQueries({ queryKey: ['theory-pending-count'] });
    qc.invalidateQueries({ queryKey: ['coding-pending-count'] });
  }

  // "Tag pending" fires BOTH namespaces (split by type server-side) up to `limit` each.
  const tagMutation = useMutation({
    mutationFn: async (limit: number) => {
      const [t, c] = await Promise.all([tagPending(limit), tagCodingPending(limit)]);
      return { enqueued: (t.enqueued ?? 0) + (c.enqueued ?? 0) };
    },
    onSuccess: invalidateTagging,
  });

  // Per-row Re-tag uses the SYNCHRONOUS single-row endpoint so the user
  // sees the LLM call complete (BusyOverlay below). Dispatch by question_type.
  const tagSingle = useMutation({
    mutationFn: ({ rowKey, qt }: { rowKey: string; qt: string }) =>
      qt === 'CODING' ? tagCodingQuestion(rowKey) : tagTheoryQuestion(rowKey),
    onSuccess: invalidateTagging,
  });

  // Selected rows may mix types — split and fire each namespace's batch endpoint.
  const tagSelected = useMutation({
    mutationFn: async (rows: { rowKey: string; qt: string }[]) => {
      const theoryKeys = rows.filter((r) => r.qt !== 'CODING').map((r) => r.rowKey);
      const codingKeys = rows.filter((r) => r.qt === 'CODING').map((r) => r.rowKey);
      const calls: Promise<{ enqueued: number }>[] = [];
      if (theoryKeys.length) calls.push(tagBatch(theoryKeys));
      if (codingKeys.length) calls.push(tagCodingBatch(codingKeys));
      const res = await Promise.all(calls);
      return { enqueued: res.reduce((n, r) => n + (r.enqueued ?? 0), 0) };
    },
    onSuccess: () => {
      setSelected(new Set());
      invalidateTagging();
    },
  });

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkLimit, setBulkLimit] = useState<number>(25);
  const [pendingTagRow, setPendingTagRow] = useState<string | null>(null);
  const [progressFor, setProgressFor] = useState<{ rowKey: string; question: string } | null>(
    null,
  );

  function toggleSelect(rowKey: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rowKey)) next.delete(rowKey);
      else next.add(rowKey);
      return next;
    });
  }

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

  const facets = facetsQ.data;
  const rawItems = listQ.data?.items ?? [];
  const items = useMemo(() => {
    if (!stage) return rawItems;
    return rawItems.filter((q) => {
      const status = q.theory?.review_status;
      if (stage === 'untagged') return !status;
      return status === stage;
    });
  }, [rawItems, stage]);
  const applied = listQ.data?.applied_date_range;
  const last = statusQ.data?.last;

  // row_key -> question_type, for dispatching tag calls to the right namespace.
  const qtByRow = useMemo(() => {
    const m = new Map<string, string>();
    for (const it of rawItems) {
      if (it.row_key) m.set(it.row_key, (it.question_type || '').toUpperCase());
    }
    return m;
  }, [rawItems]);
  const rowsForKeys = (keys: string[]) =>
    keys.map((rowKey) => ({ rowKey, qt: qtByRow.get(rowKey) || 'THEORY' }));

  return (
    <div>
      <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
        <div className="flex items-center gap-2">
          <MessagesSquare className="w-5 h-5 text-brand" />
          <h1 className="text-xl font-semibold">Interview Questions</h1>
          <span className="text-text-muted text-sm">
            {items.length} / {listQ.data?.filtered_total ?? 0}
            {listQ.data && listQ.data.filtered_total !== listQ.data.total && (
              <span className="text-text-dim"> (of {listQ.data.total} total)</span>
            )}
          </span>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <SyncBadge status={statusQ.data} />
          <NormalizeBadge
            status={normalizeStatusQ.data}
            onClick={() => normalizeMutation.mutate()}
            pending={normalizeMutation.isPending}
          />
          <button
            className="btn disabled:opacity-50"
            onClick={() => setParam('view', grouped ? 'flat' : '')}
            title="Toggle grouped vs flat view"
          >
            {grouped ? <Layers className="w-3.5 h-3.5" /> : <Rows className="w-3.5 h-3.5" />}
            {grouped ? 'Grouped' : 'Flat'}
          </button>
          {selected.size > 0 && (
            <button
              className="btn-primary disabled:opacity-50"
              disabled={tagSelected.isPending}
              onClick={() => tagSelected.mutate(rowsForKeys(Array.from(selected)))}
            >
              <Sparkles className={`w-3.5 h-3.5 ${tagSelected.isPending ? 'animate-pulse' : ''}`} />
              Tag selected ({selected.size})
            </button>
          )}
          <div className="inline-flex items-stretch border border-line rounded-md overflow-hidden">
            <select
              value={bulkLimit}
              onChange={(e) => setBulkLimit(Number(e.target.value))}
              className="bg-bg-panel text-sm text-text px-2 border-r border-line"
              title="How many pending rows to tag"
            >
              {[5, 10, 25, 50, 100, 500].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <button
              className="px-3 py-1.5 text-sm font-medium bg-bg-panel hover:bg-bg-hover disabled:opacity-50 inline-flex items-center gap-1.5"
              disabled={tagMutation.isPending}
              onClick={() => tagMutation.mutate(bulkLimit)}
              title={`Tag up to ${bulkLimit} pending THEORY rows`}
            >
              <Sparkles className={`w-3.5 h-3.5 ${tagMutation.isPending ? 'animate-pulse' : ''}`} />
              {tagMutation.isPending
                ? 'Enqueuing…'
                : `Tag pending${(() => {
                    const t = pendingCountQ.data?.by_type?.THEORY ?? pendingCountQ.data?.pending;
                    const c = codingPendingCountQ.data?.by_type?.CODING ?? codingPendingCountQ.data?.pending;
                    if (t == null && c == null) return '';
                    return ` (${t ?? 0}T · ${c ?? 0}C)`;
                  })()}`}
            </button>
          </div>
          <button
            className="btn-primary disabled:opacity-50"
            disabled={syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`}
            />
            {syncMutation.isPending ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      </div>

      {normalizeMutation.isSuccess && (
        <div className="mb-3 p-3 rounded-md border border-conf-high/40 bg-conf-high/10 text-sm text-conf-high">
          Normalize enqueued ({normalizeMutation.data.limit} groups max). Watch status badge.
        </div>
      )}
      {normalizeMutation.isError && (
        <div className="mb-3 p-3 rounded-md border border-conf-uncertain/40 bg-conf-uncertain/10 text-sm text-conf-uncertain">
          Normalize failed: {String(normalizeMutation.error)}
        </div>
      )}

      {tagMutation.isSuccess && (
        <div className="mb-3 p-3 rounded-md border border-conf-high/40 bg-conf-high/10 text-sm text-conf-high">
          Enqueued {tagMutation.data.enqueued} THEORY rows for tagging. Watch the Review Queue.
        </div>
      )}
      {tagMutation.isError && (
        <div className="mb-3 p-3 rounded-md border border-conf-uncertain/40 bg-conf-uncertain/10 text-sm text-conf-uncertain">
          Tag failed: {String(tagMutation.error)}
        </div>
      )}

      {syncMutation.isError && (
        <div className="mb-3 p-3 rounded-md border border-conf-uncertain/40 bg-conf-uncertain/10 text-sm text-conf-uncertain">
          Sync failed: {String(syncMutation.error)}
        </div>
      )}
      {deleteMutation.isError && (
        <div className="mb-3 p-3 rounded-md border border-conf-uncertain/40 bg-conf-uncertain/10 text-sm text-conf-uncertain">
          Delete failed: {String(deleteMutation.error)}
        </div>
      )}
      {deleteMutation.isSuccess && (
        <div className="mb-3 p-3 rounded-md border border-conf-high/40 bg-conf-high/10 text-sm text-conf-high">
          Deleted {deleteMutation.data.deleted_count ?? 1} interview question row
          {(deleteMutation.data.deleted_count ?? 1) > 1 ? 's' : ''}.
        </div>
      )}
      {syncMutation.isSuccess && (
        <div className="mb-3 p-3 rounded-md border border-conf-high/40 bg-conf-high/10 text-sm text-conf-high">
          Sync ok: fetched {syncMutation.data.fetched_rows} · inserted{' '}
          {syncMutation.data.inserted} · updated {syncMutation.data.updated} · unchanged{' '}
          {syncMutation.data.unchanged}
        </div>
      )}

      <div className="card p-3 mb-3">
        <DateRangeFilter
          value={{ duration, from: dateFrom, to: dateTo }}
          onChange={setDateRange}
        />
        {applied && (applied.date_from || applied.date_to) && (
          <div className="mt-2 text-xs text-text-dim flex items-center gap-2 flex-wrap">
            <span>Applied:</span>
            <span className="chip">
              {applied.date_from ?? '…'} → {applied.date_to ?? '…'}
            </span>
            <span>·</span>
            <span>{listQ.data?.filtered_total ?? 0} match the range</span>
          </div>
        )}
      </div>

      <div className="card p-3 mb-4 flex flex-wrap items-center gap-2">
        <SearchBox
          value={localQ}
          onChange={setLocalQ}
          placeholder="Search question, company, role, tech…"
        />
        <Select value={company} onChange={(v) => setParam('company', v)}>
          <option value="">Company: any</option>
          {facets?.companies.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        <Select value={role} onChange={(v) => setParam('role', v)}>
          <option value="">Role: any</option>
          {facets?.roles.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>
        <Select value={qtype} onChange={(v) => setParam('type', v)}>
          <option value="">Type: any</option>
          {facets?.question_types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <Select value={tech} onChange={(v) => setParam('tech', v)}>
          <option value="">Tech: any</option>
          {facets?.tech_stacks.map((t) => (
            <option key={t} value={t}>
              {t.length > 40 ? t.slice(0, 40) + '…' : t}
            </option>
          ))}
        </Select>
        <Select value={product} onChange={(v) => setParam('product', v)}>
          <option value="">Product: any</option>
          {facets?.products.map((p) => (
            <option key={p} value={p}>
              {p.length > 40 ? p.slice(0, 40) + '…' : p}
            </option>
          ))}
        </Select>
        <Select value={stage} onChange={(v) => setParam('stage', v)}>
          <option value="">Stage: any</option>
          <option value="approved">Approved</option>
          <option value="needs_review">Needs review</option>
          <option value="pending">Pending</option>
          <option value="rejected">Rejected</option>
          <option value="untagged">Untagged</option>
        </Select>
        {(q || company || role || qtype || tech || product || stage) && (
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
          title="No interview questions match"
          hint="Adjust filters, or trigger a sync if the DB is empty."
        />
      )}

      {items.length > 0 && (
        <div className="card divide-y divide-line overflow-hidden">
          {items.map((q) => {
            const qt = (q.question_type || '').toUpperCase();
            const isTaggable = qt === 'THEORY' || qt === 'CODING';
            const theory = q.theory;
            const isPendingTag =
              pendingTagRow === q.row_key ||
              (tagSingle.isPending && tagSingle.variables?.rowKey === q.row_key);
            const isSelected = selected.has(q.row_key);
            return (
              <div
                key={q.id}
                className={`p-4 transition-colors ${
                  isSelected ? 'bg-brand/5' : 'hover:bg-bg-hover'
                }`}
              >
                <div className="flex items-start gap-3">
                  {isTaggable ? (
                    <button
                      onClick={() => toggleSelect(q.row_key)}
                      className="mt-1 text-text-dim hover:text-brand"
                      title={isSelected ? 'Deselect' : 'Select for bulk tag'}
                    >
                      {isSelected ? (
                        <CheckSquare className="w-4 h-4 text-brand" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                    </button>
                  ) : (
                    <div className="w-4 h-4 mt-1" />
                  )}
                  <div className="text-brand mt-1 shrink-0">
                    {q.question_type === 'CODING' ? (
                      <Code2 className="w-4 h-4" />
                    ) : (
                      <MessagesSquare className="w-4 h-4" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    {isTaggable ? (
                      <Link
                        to={`/courses/programming_foundations/theory-questions/${encodeURIComponent(
                          q.row_key,
                        )}${qt === 'CODING' ? '?type=coding' : ''}`}
                        className="block text-text leading-relaxed whitespace-pre-wrap break-words hover:text-brand"
                        title="Open detail (AI reasoning, citations, synthesized answer)"
                      >
                        {q.question}
                      </Link>
                    ) : (
                      <p className="text-text leading-relaxed whitespace-pre-wrap break-words">
                        {q.question}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-text-muted">
                      {q.interview_date && (
                        <span
                          className="chip border-brand/40 text-brand bg-brand/5 font-medium"
                          title={q.interview_date}
                        >
                          <Calendar className="w-3 h-3" /> Interview round: {fmtInterviewDate(q.interview_date)}
                        </span>
                      )}
                      {q.company_name && (
                        <span className="chip">
                          <Building2 className="w-3 h-3" /> {q.company_name}
                        </span>
                      )}
                      {q.role && (
                        <span className="chip">
                          <Briefcase className="w-3 h-3" /> {q.role}
                        </span>
                      )}
                      {q.question_type && <span className="chip">{q.question_type}</span>}
                      {q.tech_stack && (
                        <span className="chip max-w-[260px] truncate" title={q.tech_stack}>
                          {q.tech_stack}
                        </span>
                      )}
                      {q.product && (
                        <span className="chip max-w-[180px] truncate" title={q.product}>
                          {q.product}
                        </span>
                      )}
                      {(q.member_count ?? 1) > 1 && q.group_key && (
                        <AskedChip
                          count={q.member_count}
                          onClick={() => setOpenGroup(q.group_key as string)}
                        />
                      )}
                      {q.canonical_question && (
                        <span className="chip" title={q.canonical_question}>
                          canonical
                        </span>
                      )}
                    </div>
                    {q.skills_assessed_remarks && (
                      <div className="text-xs text-text-dim mt-2 leading-relaxed">
                        <span className="font-medium text-text-muted">Skills: </span>
                        {q.skills_assessed_remarks}
                      </div>
                    )}
                    {q.remarks && (
                      <div className="text-xs text-text-dim mt-1 leading-relaxed">
                        <span className="font-medium text-text-muted">Remarks: </span>
                        {q.remarks}
                      </div>
                    )}
                  </div>
                  {isTaggable && (
                    <div className="flex flex-col items-end gap-1.5 shrink-0 min-w-[170px]">
                      {theory ? (
                        <Link
                          to={`/courses/programming_foundations/theory-questions/${encodeURIComponent(
                            theory.row_key as string,
                          )}${qt === 'CODING' ? '?type=coding' : ''}`}
                          className="flex flex-col items-end gap-1"
                          title="Open tag detail"
                        >
                          <VerdictBadge verdict={(theory.verdict ?? 'not_covered') as any} />
                          <ConfidenceBar value={Number(theory.overall_confidence ?? 0)} />
                          <span className="text-[10px] text-text-dim font-mono">
                            {theory.review_status}
                          </span>
                          {theory.synthesis_quality &&
                            theory.synthesis_quality !== 'skipped' && (
                              <span
                                className={`text-[10px] font-mono ${
                                  theory.synthesis_quality === 'complete'
                                    ? 'text-conf-covered'
                                    : theory.synthesis_quality === 'partial'
                                    ? 'text-conf-medium'
                                    : 'text-conf-uncertain'
                                }`}
                                title="Synthesizer quality"
                              >
                                synth: {theory.synthesis_quality}
                              </span>
                            )}
                        </Link>
                      ) : null}
                      <button
                        className="btn text-xs disabled:opacity-50 mt-1"
                        disabled={isPendingTag}
                        onClick={() => {
                          setPendingTagRow(q.row_key);
                          setProgressFor({ rowKey: q.row_key, question: q.question || '' });
                          tagSingle.mutate(
                            { rowKey: q.row_key, qt },
                            { onSettled: () => setPendingTagRow(null) },
                          );
                        }}
                        title={theory ? 'Re-tag this question' : 'Tag this question now'}
                      >
                        {isPendingTag ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Tag className="w-3 h-3" />
                        )}
                        {isPendingTag ? 'Tagging…' : theory ? 'Re-tag' : 'Tag now'}
                      </button>
                      <button
                        className="btn text-xs text-conf-uncertain border-conf-uncertain/40 hover:bg-conf-uncertain/10 disabled:opacity-50"
                        disabled={deleteMutation.isPending}
                        onClick={() => {
                          const ok = window.confirm(
                            'Delete this interview question and its related tagging/workflow records?',
                          );
                          if (!ok) return;
                          deleteMutation.mutate(q.row_key);
                        }}
                        title="Delete before approving/tagging"
                      >
                        <Trash2 className="w-3 h-3" />
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {last && (
        <div className="mt-4 text-xs text-text-dim flex items-center gap-2">
          <Clock className="w-3 h-3" />
          Last sync ({last.trigger}): {fmtDate(last.started_at)} ·{' '}
          inserted {last.inserted} · updated {last.updated} · unchanged {last.unchanged}
        </div>
      )}

      {progressFor && (
        <TagProgressModal
          rowKey={progressFor.rowKey}
          questionText={progressFor.question}
          open={!!progressFor}
          active={tagSingle.isPending}
          onClose={() => setProgressFor(null)}
        />
      )}

      {openGroup && (
        <GroupMembersModal groupKey={openGroup} onClose={() => setOpenGroup(null)} />
      )}
    </div>
  );
}

function NormalizeBadge({
  status,
  onClick,
  pending,
}: {
  status?: { pending: number; normalized: number; merged: number; total: number };
  onClick: () => void;
  pending: boolean;
}) {
  if (!status) return null;
  const hasPending = status.pending > 0;
  return (
    <button
      className={`chip ${hasPending ? 'border-conf-medium/50 text-conf-medium' : 'chip-on'} disabled:opacity-50`}
      onClick={onClick}
      disabled={pending}
      title="Run DSPy semantic normalizer over groups that haven't been canonicalized yet"
    >
      <Wand2 className={`w-3 h-3 ${pending ? 'animate-pulse' : ''}`} />
      {pending ? 'Normalizing…' : `Normalize: ${status.pending} pending · ${status.normalized} done · ${status.merged} merged`}
    </button>
  );
}

function SyncBadge({ status }: { status?: { last: any; schedule: any } }) {
  if (!status) return null;
  const last = status.last;
  const sched = status.schedule;
  if (!last) {
    return (
      <span className="chip">
        <Clock className="w-3 h-3" />
        Daily {pad(sched.hour_utc)}:{pad(sched.minute_utc)} UTC · never synced
      </span>
    );
  }
  const ok = last.status === 'success';
  return (
    <span className={ok ? 'chip-on' : 'chip'}>
      {ok ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
      Last: {fmtDate(last.started_at)} · daily {pad(sched.hour_utc)}:{pad(sched.minute_utc)} UTC
    </span>
  );
}

function Select({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="input text-sm max-w-[200px]">
      {children}
    </select>
  );
}

function pad(n: number) {
  return String(n).padStart(2, '0');
}

function fmtDate(iso: string | null | undefined) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function fmtInterviewDate(s: string | null | undefined) {
  if (!s) return '';
  const t = s.length >= 10 ? s.slice(0, 10) : s;
  const d = new Date(t);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}
