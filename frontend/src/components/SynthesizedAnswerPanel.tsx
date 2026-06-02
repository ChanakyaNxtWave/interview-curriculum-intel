import { useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

type Quality = 'complete' | 'partial' | 'insufficient' | 'skipped' | string;
type Strategy =
  | 'exact_match'
  | 'partial_match'
  | 'combined'
  | 'none'
  | ''
  | string;

interface GroundingEntry {
  claim: string;
  content_ids: string[];
}

interface Props {
  answer?: string | null;
  grounding?: GroundingEntry[];
  quality?: Quality;
  confidence?: number;
  reasoning?: string | null;
  questionType?: string;
  matchStrategy?: Strategy;
}

function qualityChip(q: Quality) {
  if (q === 'complete') {
    return {
      icon: <CheckCircle2 className="w-3.5 h-3.5" />,
      label: 'complete',
      cls: 'border-conf-covered/50 text-conf-covered bg-conf-covered/10',
    };
  }
  if (q === 'partial') {
    return {
      icon: <AlertTriangle className="w-3.5 h-3.5" />,
      label: 'partial',
      cls: 'border-conf-medium/50 text-conf-medium bg-conf-medium/10',
    };
  }
  if (q === 'insufficient') {
    return {
      icon: <XCircle className="w-3.5 h-3.5" />,
      label: 'insufficient',
      cls: 'border-conf-uncertain/50 text-conf-uncertain bg-conf-uncertain/10',
    };
  }
  return {
    icon: null,
    label: String(q || 'unknown'),
    cls: 'border-line text-text-muted bg-bg-panel',
  };
}

function strategyLabel(s: Strategy): string {
  if (!s || s === 'none') return '';
  if (s === 'exact_match') return 'exact match';
  if (s === 'partial_match') return 'partial match';
  if (s === 'combined') return 'combined solutions';
  return String(s);
}

export default function SynthesizedAnswerPanel({
  answer,
  grounding,
  quality,
  confidence,
  reasoning,
  questionType,
  matchStrategy,
}: Props) {
  const [showReasoning, setShowReasoning] = useState(false);
  if (!quality || quality === 'skipped') return null;
  const chip = qualityChip(quality);
  const isCoding = (questionType || '').toUpperCase() === 'CODING';
  const stratLabel = strategyLabel(matchStrategy ?? '');
  const groundingList = grounding ?? [];

  return (
    <div className="card p-4 mt-3 border border-brand/30 bg-brand/5">
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-brand" />
          <h3 className="text-sm font-semibold text-text">Curriculum Answer</h3>
          <span
            className={`chip ${chip.cls} text-xs inline-flex items-center gap-1`}
            title="synthesizer quality"
          >
            {chip.icon}
            {chip.label}
          </span>
          {typeof confidence === 'number' && (
            <span className="text-xs text-text-dim">
              · synth conf {(confidence * 100).toFixed(0)}%
            </span>
          )}
          {isCoding && stratLabel && (
            <span className="chip border-brand/40 text-brand bg-brand/5 text-xs">
              {stratLabel}
            </span>
          )}
        </div>
      </div>

      {answer ? (
        <div className="prose prose-invert max-w-none text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
        </div>
      ) : (
        <div className="text-sm text-text-muted italic">
          No answer produced. Open citations directly to verify coverage.
        </div>
      )}

      {groundingList.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-text-dim uppercase tracking-wide mb-1">
            Grounding (each claim → supporting citations)
          </div>
          <ul className="space-y-1.5 text-xs">
            {groundingList.map((g, i) => (
              <li key={i} className="flex flex-wrap items-start gap-1.5">
                <span className="text-text">{g.claim}</span>
                {(g.content_ids ?? []).map((cid) => (
                  <Link
                    key={cid}
                    to={`/content/${encodeURIComponent(cid)}`}
                    className="chip border-brand/40 text-brand bg-brand/5 hover:bg-brand/10 font-mono"
                    title="Open citation"
                  >
                    {cid.slice(0, 8)}…
                  </Link>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}

      {reasoning && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowReasoning((v) => !v)}
            className="text-xs text-text-muted hover:text-text inline-flex items-center gap-1"
          >
            {showReasoning ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
            Show synthesizer reasoning
          </button>
          {showReasoning && (
            <pre className="mt-2 p-2 bg-bg-panel/60 border border-line rounded text-xs text-text-muted whitespace-pre-wrap break-words">
              {reasoning}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
