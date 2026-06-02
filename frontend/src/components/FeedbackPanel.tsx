import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, MessageSquarePlus, Send } from 'lucide-react';
import {
  fetchFeedback,
  submitFeedback,
  type FeedbackPayload,
} from '../api/theory';
import { fetchCodingFeedback, submitCodingFeedback } from '../api/coding';
import type { FeedbackEntry, FeedbackSeverity, FeedbackType } from '../api/types';

const TYPES: { value: FeedbackType; label: string }[] = [
  { value: 'wrong_verdict', label: 'Wrong verdict' },
  { value: 'missing_kp', label: 'Missing KP' },
  { value: 'wrong_kp', label: 'Wrong KP' },
  { value: 'missing_citation', label: 'Missing citation' },
  { value: 'wrong_citation', label: 'Wrong citation' },
  { value: 'general', label: 'General' },
];

const SEVERITIES: { value: FeedbackSeverity; label: string; cls: string }[] = [
  { value: 'low', label: 'Low', cls: 'border-text-dim text-text-muted' },
  { value: 'medium', label: 'Medium', cls: 'border-conf-medium/50 text-conf-medium' },
  { value: 'high', label: 'High', cls: 'border-conf-uncertain/50 text-conf-uncertain' },
];

export default function FeedbackPanel({
  rowKey,
  activePromptVersion,
  isCoding = false,
}: {
  rowKey: string;
  activePromptVersion?: string;
  isCoding?: boolean;
}) {
  const qc = useQueryClient();
  const [type, setType] = useState<FeedbackType>('wrong_verdict');
  const [severity, setSeverity] = useState<FeedbackSeverity>('medium');
  const [text, setText] = useState('');

  const listQ = useQuery({
    queryKey: ['feedback', rowKey, isCoding],
    queryFn: () => (isCoding ? fetchCodingFeedback(rowKey) : fetchFeedback(rowKey)),
  });

  const submit = useMutation({
    mutationFn: (payload: FeedbackPayload) =>
      isCoding ? submitCodingFeedback(rowKey, payload) : submitFeedback(rowKey, payload),
    onSuccess: () => {
      setText('');
      qc.invalidateQueries({ queryKey: ['feedback', rowKey, isCoding] });
    },
  });

  function send() {
    const trimmed = text.trim();
    if (!trimmed) return;
    submit.mutate({ feedback_type: type, feedback_text: trimmed, severity });
  }

  const items: FeedbackEntry[] = listQ.data?.feedback ?? [];

  return (
    <div className="card p-4 mb-4">
      <div className="flex items-center gap-2 mb-3">
        <MessageSquarePlus className="w-4 h-4 text-brand" />
        <h2 className="font-semibold text-text">Feedback to LLM</h2>
        <span className="text-xs text-text-dim">
          High-severity feedback gets 3× weight in next DSPy recompile
          {activePromptVersion ? ` (active: ${activePromptVersion})` : ''}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label className="text-xs text-text-dim block mb-1">Type</label>
          <select
            className="input w-full"
            value={type}
            onChange={(e) => setType(e.target.value as FeedbackType)}
          >
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-text-dim block mb-1">Severity</label>
          <div className="flex gap-1.5">
            {SEVERITIES.map((s) => (
              <button
                key={s.value}
                onClick={() => setSeverity(s.value)}
                className={`flex-1 px-2 py-1.5 rounded-md text-sm border ${
                  severity === s.value
                    ? `${s.cls} bg-bg-hover`
                    : 'border-line text-text-muted hover:bg-bg-hover'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <textarea
        className="input w-full min-h-[80px] mb-3"
        placeholder="What did the LLM get wrong? Be specific — this guides next compile."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="flex items-center gap-3">
        <button
          className="btn-primary disabled:opacity-50"
          disabled={submit.isPending || !text.trim()}
          onClick={send}
        >
          {submit.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Send className="w-3.5 h-3.5" />
          )}
          {submit.isPending ? 'Sending…' : 'Send feedback'}
        </button>
        {submit.isError && (
          <span className="text-sm text-conf-uncertain">{String(submit.error)}</span>
        )}
        {submit.isSuccess && (
          <span className="text-sm text-conf-high">Saved · weights into next recompile</span>
        )}
      </div>

      {listQ.isLoading && (
        <div className="mt-3 text-xs text-text-dim flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading past feedback…
        </div>
      )}

      {items.length > 0 && (
        <div className="mt-4 pt-4 border-t border-line">
          <div className="text-xs text-text-dim uppercase tracking-wide mb-2">
            Past feedback ({items.length})
          </div>
          <div className="space-y-2">
            {items.map((f) => (
              <div key={f.id} className="p-2.5 rounded-md border border-line bg-bg-panel">
                <div className="flex items-center gap-2 flex-wrap text-xs">
                  <span className="font-mono text-text-dim">{f.feedback_type}</span>
                  <SeverityChip severity={f.severity as FeedbackSeverity} />
                  <span className="text-text-dim ml-auto">
                    {new Date(f.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-sm text-text mt-1.5 whitespace-pre-wrap">
                  {f.feedback_text}
                </p>
                {f.prompt_version && (
                  <div className="text-[11px] text-text-dim mt-1 font-mono">
                    sent vs {f.prompt_version}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SeverityChip({ severity }: { severity: FeedbackSeverity }) {
  const cls =
    severity === 'high'
      ? 'bg-conf-uncertain/15 border-conf-uncertain/40 text-conf-uncertain'
      : severity === 'medium'
        ? 'bg-conf-medium/15 border-conf-medium/40 text-conf-medium'
        : 'bg-bg-hover border-line text-text-muted';
  return <span className={`chip ${cls}`}>{severity}</span>;
}
