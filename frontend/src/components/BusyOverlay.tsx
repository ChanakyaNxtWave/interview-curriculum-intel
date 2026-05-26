import { Loader2 } from 'lucide-react';

export default function BusyOverlay({
  label,
  hint,
  show,
}: {
  label: string;
  hint?: string;
  show: boolean;
}) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm flex items-center justify-center pointer-events-none">
      <div className="card px-5 py-4 flex items-center gap-3 shadow-2xl">
        <Loader2 className="w-5 h-5 text-brand animate-spin" />
        <div>
          <div className="text-text font-medium">{label}</div>
          {hint && <div className="text-xs text-text-dim">{hint}</div>}
        </div>
      </div>
    </div>
  );
}

export function InlineSpinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-text-muted">
      <Loader2 className="w-3.5 h-3.5 animate-spin text-brand" />
      {label ?? 'Loading…'}
    </span>
  );
}
