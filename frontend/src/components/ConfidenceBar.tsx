export default function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const high = value >= 0.85;
  const mid = value >= 0.5 && value < 0.85;
  const fill = high ? 'bg-conf-high' : mid ? 'bg-conf-medium' : 'bg-conf-uncertain';
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 rounded-full bg-bg-panel overflow-hidden">
        <div className={`h-full ${fill}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-text-muted tabular-nums w-9 text-right">{pct}%</span>
    </div>
  );
}
