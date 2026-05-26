import type { ConfidenceLevel } from '../api/types';

const CLS: Record<ConfidenceLevel, string> = {
  high: 'bg-conf-high/15 text-conf-high border-conf-high/40',
  medium: 'bg-conf-medium/15 text-conf-medium border-conf-medium/40',
  low: 'bg-conf-low/15 text-conf-low border-conf-low/40',
  uncertain: 'bg-conf-uncertain/15 text-conf-uncertain border-conf-uncertain/40',
};

export default function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${CLS[level] ?? CLS.uncertain}`}>
      {level}
    </span>
  );
}
