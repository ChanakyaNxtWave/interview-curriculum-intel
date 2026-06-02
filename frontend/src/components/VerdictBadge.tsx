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

export default function VerdictBadge({ verdict }: { verdict: TheoryVerdict | string }) {
  const s = STYLE[(verdict as TheoryVerdict)] ?? STYLE.not_covered;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${s.cls}`}>
      {s.icon}
      {s.label}
    </span>
  );
}
