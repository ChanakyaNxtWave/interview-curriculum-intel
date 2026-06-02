import type { TheoryVerdict } from '../api/types';
import { CheckCircle2, XCircle } from 'lucide-react';

const STYLE: Record<TheoryVerdict, { cls: string; label: string; icon: React.ReactNode }> = {
  covered: {
    cls: 'bg-conf-high/15 text-conf-high border-conf-high/40',
    label: 'covered',
    icon: <CheckCircle2 className="w-3 h-3" />,
  },
  not_covered: {
    cls: 'bg-conf-uncertain/15 text-conf-uncertain border-conf-uncertain/40',
    label: 'not covered',
    icon: <XCircle className="w-3 h-3" />,
  },
};

function normalizeVerdict(verdict: string): TheoryVerdict {
  if (verdict === 'covered') return 'covered';
  // Legacy pipeline values collapse to not_covered in the UI.
  if (verdict === 'not_covered' || verdict === 'partially_covered' || verdict === 'uncertain') {
    return 'not_covered';
  }
  return 'not_covered';
}

export default function VerdictBadge({ verdict }: { verdict: TheoryVerdict | string }) {
  const s = STYLE[normalizeVerdict(verdict)] ?? STYLE.not_covered;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${s.cls}`}>
      {s.icon}
      {s.label}
    </span>
  );
}
