import type { TheoryVerdict } from '../api/types';

/** Verdict shown in lists and headers — human review wins over AI. */
export function effectiveVerdict(item: {
  human_verdict?: string | null;
  verdict?: string | null;
}): TheoryVerdict {
  return (item.human_verdict ?? item.verdict ?? 'not_covered') as TheoryVerdict;
}
