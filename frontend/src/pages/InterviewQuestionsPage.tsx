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
  triggerInterviewSync,
  deleteInterviewQuestion,
} from '../api/interview';
import { tagBatch } from '../api/theory';
import { tagCodingBatch } from '../api/coding';
import { useAsyncTag } from '../hooks/useAsyncTag';
import { CheckSquare, Loader2, Sparkles, Square, Tag } from 'lucide-react';
import VerdictBadge from '../components/VerdictBadge';
import { effectiveVerdict } from '../lib/verdict';
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
        group_by: true,
        limit: 1000,
      }),
  });

  const syncMutation = useMutation({
    mutationFn: triggerInterviewSync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['interview-list'] });
      qc.invalidateQueries({ queryKey: ['interview-facets'] });
      qc.invalidateQueries({ queryKey: ['interview-sync-status'] });
      qc.invalidateQueries({ queryKey: ['theory-list'] });
      qc.invalidateQueries({ queryKey: ['coding-list'] });
      qc.invalidateQueries({ queryKey: ['review-queue'] });
      qc.invalidateQueries({ queryKey: ['review-count'] });
      qc.invalidateQueries({ queryKey: ['course-grouped-questions'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (rowKey: string) => deleteInterviewQuestion(rowKey),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['interview-list'] });
      qc.invalidateQueries({ queryKey: ['interview-facets'] });
      qc.invalidateQueries({ queryKey: ['theory-list'] });
      qc.invalidateQueries({ queryKey: ['coding-list'] });
      qc.invalidateQueries({ queryKey: ['review-queue'] });
      qc.invalidateQueries({ queryKey: ['review-count'] });
      qc.invalidateQueries({ queryKey: ['theory-pending-count'] });
      qc.invalidateQueries({ queryKey: ['coding-pending-count'] });
    },
  });

  function invalidateTagging() {
    qc.invalidateQueries({ queryKey: ['theory-list'] });
    qc.invalidateQueries({ queryKey: ['coding-list'] });
    qc.invalidateQueries({ queryKey: ['review-queue'] });
    qc.invalidateQueries({ queryKey: ['review-count'] });
    qc.invalidateQueries({ queryKey: ['interview-list'] });
    qc.invalidateQueries({ queryKey: ['course-grouped-questions'] });
  }

  const asyncTag = useAsyncTag(invalidateTagging);

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
              asyncTag.pendingRowKey === q.row_key ||
              asyncTag.session?.requestedRowKey === q.row_key ||
              (asyncTag.session?.tracking &&
                asyncTag.session.tagRowKey === (q.theory?.row_key as string | undefined));
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
                          <VerdictBadge verdict={effectiveVerdict(theory)} />
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
                        onClick={() => asyncTag.beginTag(q.row_key, qt, q.question || '')}
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

      {asyncTag.session && (
        <TagProgressModal
          rowKey={asyncTag.session.tagRowKey}
          questionText={asyncTag.session.questionText}
          open
          tracking={asyncTag.session.tracking}
          isCoding={asyncTag.session.isCoding}
          onClose={asyncTag.finishTag}
          onComplete={asyncTag.finishTag}
        />
      )}

      {openGroup && (
        <GroupMembersModal groupKey={openGroup} onClose={() => setOpenGroup(null)} />
      )}
    </div>
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
