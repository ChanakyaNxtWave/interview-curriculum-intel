import { CalendarRange } from 'lucide-react';

export type DurationPreset = '' | '1m' | '3m' | '6m' | '12m' | 'custom';

export interface DateRangeValue {
  duration: DurationPreset;
  from: string;
  to: string;
}

const PRESETS: { value: DurationPreset; label: string }[] = [
  { value: '', label: 'All time' },
  { value: '1m', label: 'Last 1 month' },
  { value: '3m', label: 'Last 3 months' },
  { value: '6m', label: 'Last 6 months' },
  { value: '12m', label: 'Last 12 months' },
  { value: 'custom', label: 'Custom range' },
];

export default function DateRangeFilter({
  value,
  onChange,
  label = 'Duration',
}: {
  value: DateRangeValue;
  onChange: (v: DateRangeValue) => void;
  label?: string;
}) {
  function setPreset(p: DurationPreset) {
    if (p === '' || p === 'custom') {
      onChange({ duration: p, from: '', to: '' });
    } else {
      onChange({ duration: p, from: '', to: '' });
    }
  }

  function setFrom(v: string) {
    onChange({ ...value, duration: 'custom', from: v });
  }

  function setTo(v: string) {
    onChange({ ...value, duration: 'custom', to: v });
  }

  const showDates = value.duration === 'custom';

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="inline-flex items-center gap-1 text-xs text-text-dim">
        <CalendarRange className="w-3.5 h-3.5" />
        {label}:
      </span>
      <select
        value={value.duration}
        onChange={(e) => setPreset(e.target.value as DurationPreset)}
        className="input text-sm"
      >
        {PRESETS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>
      {showDates && (
        <>
          <input
            type="date"
            value={value.from}
            onChange={(e) => setFrom(e.target.value)}
            className="input text-sm"
            aria-label="Start date"
          />
          <span className="text-text-dim text-xs">→</span>
          <input
            type="date"
            value={value.to}
            onChange={(e) => setTo(e.target.value)}
            className="input text-sm"
            aria-label="End date"
          />
        </>
      )}
    </div>
  );
}
