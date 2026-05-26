import { Users } from 'lucide-react';

export default function AskedChip({
  count,
  onClick,
}: {
  count: number | null | undefined;
  onClick?: (e: React.MouseEvent) => void;
}) {
  if (!count || count <= 1) return null;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick?.(e);
      }}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-brand/15 border border-brand/40 text-brand hover:bg-brand/25 transition-colors"
      title={`Same question asked ${count} times — click to see members`}
    >
      <Users className="w-3 h-3" />
      Asked {count}×
    </button>
  );
}
