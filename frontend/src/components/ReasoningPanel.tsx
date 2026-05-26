import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, ChevronDown, ChevronRight, Lightbulb, XCircle } from 'lucide-react';
import type { TheoryCitation, TheoryRequiredKp } from '../api/types';

interface Props {
  kpReasoning?: string | null;
  judgeReasoning?: string | null;
  rationale?: string | null;
  requiredKps?: TheoryRequiredKp[];
  rejectedCandidates?: TheoryCitation[];
}

export default function ReasoningPanel({
  kpReasoning,
  judgeReasoning,
  rationale,
  requiredKps = [],
  rejectedCandidates = [],
}: Props) {
  const [open, setOpen] = useState(true);
  const empty =
    !kpReasoning &&
    !judgeReasoning &&
    !rationale &&
    requiredKps.length === 0 &&
    rejectedCandidates.length === 0;
  if (empty) return null;

  return (
    <div className="card mb-4 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-bg-hover transition-colors text-left"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-text-dim" />
        ) : (
          <ChevronRight className="w-4 h-4 text-text-dim" />
        )}
        <Brain className="w-4 h-4 text-brand" />
        <span className="font-semibold text-text">AI Reasoning</span>
        <span className="text-xs text-text-dim ml-2">
          how the pipeline arrived at the verdict
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-line">
          {kpReasoning && (
            <Section title="KP identification (chain of thought)" icon={<Lightbulb className="w-3.5 h-3.5" />}>
              <p className="text-sm text-text whitespace-pre-wrap leading-relaxed">{kpReasoning}</p>
              {requiredKps.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {requiredKps.map((k) => (
                    <li key={k.source_kp_id} className="text-xs text-text-muted">
                      <span className="font-mono text-brand mr-2">{k.source_kp_id}</span>
                      {k.confidence && <span className="chip mr-2">{k.confidence}</span>}
                      {k.rationale}
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          )}

          {judgeReasoning && (
            <Section title="Coverage judge (chain of thought)" icon={<Brain className="w-3.5 h-3.5" />}>
              <p className="text-sm text-text whitespace-pre-wrap leading-relaxed">
                {judgeReasoning}
              </p>
              {rationale && (
                <p className="text-sm text-text-muted mt-3 pt-3 border-t border-line whitespace-pre-wrap">
                  <span className="text-text-dim text-xs uppercase tracking-wide block mb-1">
                    Final rationale
                  </span>
                  {rationale}
                </p>
              )}
            </Section>
          )}

          {!judgeReasoning && rationale && (
            <Section title="AI rationale" icon={<Brain className="w-3.5 h-3.5" />}>
              <p className="text-sm text-text whitespace-pre-wrap leading-relaxed">{rationale}</p>
            </Section>
          )}

          {rejectedCandidates.length > 0 && (
            <Section
              title={`Candidates the judge rejected (${rejectedCandidates.length})`}
              icon={<XCircle className="w-3.5 h-3.5" />}
            >
              <p className="text-xs text-text-dim mb-2">
                Citations retrieved for the required KPs but NOT accepted by the coverage judge.
              </p>
              <div className="space-y-2">
                {rejectedCandidates.map((c) => (
                  <div
                    key={c.content_id}
                    className="p-2.5 rounded-md border border-line bg-bg-panel/60 opacity-75"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link
                        to={`/content/${encodeURIComponent(c.content_id)}`}
                        className="text-sm text-text hover:text-brand truncate"
                      >
                        {c.title ?? c.content_id}
                      </Link>
                      {c.kp_id && <span className="chip">{c.kp_id}</span>}
                      {c.tag_role && <span className="chip">{c.tag_role}</span>}
                    </div>
                    {c.snippet && (
                      <p className="text-xs text-text-dim mt-1 line-clamp-2 font-mono">
                        {c.snippet}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-text-dim text-xs uppercase tracking-wide mb-2">
        {icon}
        {title}
      </div>
      <div className="rounded-md border border-line bg-bg-panel p-3">{children}</div>
    </div>
  );
}
