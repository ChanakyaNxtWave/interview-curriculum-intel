import { Inbox } from 'lucide-react';

export default function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="card flex flex-col items-center justify-center py-16 text-center">
      <Inbox className="w-10 h-10 text-text-dim mb-3" />
      <div className="text-text font-medium">{title}</div>
      {hint && <div className="text-text-muted text-sm mt-1">{hint}</div>}
    </div>
  );
}
