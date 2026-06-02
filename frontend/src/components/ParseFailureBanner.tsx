import { Link } from 'react-router-dom';
import { AlertOctagon } from 'lucide-react';

const PARSE_PREFIX = 'pipeline_error: Adapter JSONAdapter failed to parse';

const COURSE_ID = 'programming_foundations';

export function detectParseFailure(reasons: string[] | undefined | null): {
  failed: boolean;
  errorText: string;
  recoveredKps: string[];
} {
  const list = reasons ?? [];
  const errorReason = list.find((r) => r?.startsWith(PARSE_PREFIX)) ?? '';
  if (!errorReason) return { failed: false, errorText: '', recoveredKps: [] };
  const found = errorReason.match(/KP_GLOBAL_\d{4}/g) ?? [];
  // Dedupe preserving order
  const seen = new Set<string>();
  const recoveredKps: string[] = [];
  for (const k of found) {
    if (!seen.has(k)) {
      seen.add(k);
      recoveredKps.push(k);
    }
  }
  return { failed: true, errorText: errorReason, recoveredKps };
}

export default function ParseFailureBanner({
  reasons,
  compact = false,
}: {
  reasons: string[] | undefined | null;
  compact?: boolean;
}) {
  const { failed, recoveredKps } = detectParseFailure(reasons);
  if (!failed) return null;
  return (
    <div
      className={`rounded-md border border-conf-uncertain/50 bg-conf-uncertain/10 ${
        compact ? 'p-2 text-xs' : 'p-3 text-sm'
      } space-y-1.5`}
    >
      <div className="flex items-center gap-1.5 font-semibold text-conf-uncertain">
        <AlertOctagon className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
        LM output corrupted (JSON parse failure)
      </div>
      {recoveredKps.length > 0 ? (
        <>
          <div className="text-text-muted">
            LM named these KPs in its reasoning but the structured output corrupted:
          </div>
          <div className="flex flex-wrap gap-1">
            {recoveredKps.map((kp) => (
              <Link
                key={kp}
                to={`/courses/${COURSE_ID}/kps/${encodeURIComponent(kp)}`}
                className="chip border-brand/40 text-brand bg-brand/5 hover:bg-brand/10"
                title="Open KP detail"
              >
                {kp}
              </Link>
            ))}
          </div>
          <div className="text-text-dim">
            Re-tag now (model is back on Sonnet) or hand-pick these in the KP editor.
          </div>
        </>
      ) : (
        <div className="text-text-muted">
          No KP IDs could be recovered from reasoning. Re-tag to retry.
        </div>
      )}
    </div>
  );
}
