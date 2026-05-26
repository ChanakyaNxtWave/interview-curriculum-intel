import { useQuery } from '@tanstack/react-query';
import { X, Calendar, Briefcase, Loader2 } from 'lucide-react';
import { fetchGroupMembers } from '../api/interview';

export default function GroupMembersModal({
  groupKey,
  onClose,
}: {
  groupKey: string;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['group-members', groupKey],
    queryFn: () => fetchGroupMembers(groupKey),
  });

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="card max-w-3xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-line sticky top-0 bg-bg-card z-10">
          <div className="min-w-0">
            <h3 className="font-semibold text-text">Question members</h3>
            <div className="text-xs text-text-dim mt-0.5 font-mono truncate">{groupKey}</div>
          </div>
          <button onClick={onClose} className="text-text-dim hover:text-text" aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {isLoading && (
            <div className="flex items-center gap-2 text-text-muted text-sm">
              <Loader2 className="w-4 h-4 animate-spin text-brand" /> Loading members…
            </div>
          )}
          {error && <div className="text-conf-uncertain text-sm">{String(error)}</div>}

          {data && (
            <>
              <div className="rounded-md border border-line bg-bg-panel p-3">
                <div className="text-xs text-text-dim uppercase tracking-wide mb-1">
                  {data.group.canonical_question ? 'Canonical' : 'Exact'}
                </div>
                <p className="text-sm text-text whitespace-pre-wrap">
                  {data.group.canonical_question ?? data.group.exact_question}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {data.group.company_name && <span className="chip">{data.group.company_name}</span>}
                  {data.group.canonical_slug && (
                    <span className="chip font-mono">{data.group.canonical_slug}</span>
                  )}
                  <span className="chip">{data.group.member_count} members</span>
                  {data.group.normalized ? (
                    <span className="chip-on">normalized</span>
                  ) : (
                    <span className="chip">not normalized</span>
                  )}
                </div>
              </div>

              <div>
                <div className="text-xs text-text-dim uppercase tracking-wide mb-1.5">
                  Members ({data.members.length})
                </div>
                <div className="space-y-2">
                  {data.members.map((m) => (
                    <div
                      key={m.row_key}
                      className={`p-2.5 rounded-md border ${
                        m.row_key === data.group.representative_row_key
                          ? 'border-brand/50 bg-brand/5'
                          : 'border-line bg-bg-panel'
                      }`}
                    >
                      <div className="flex items-center gap-2 flex-wrap text-xs text-text-muted">
                        {m.row_key === data.group.representative_row_key && (
                          <span className="chip-on">representative</span>
                        )}
                        {m.role && (
                          <span className="chip">
                            <Briefcase className="w-3 h-3" /> {m.role}
                          </span>
                        )}
                        {m.interview_date && (
                          <span className="chip">
                            <Calendar className="w-3 h-3" /> {m.interview_date}
                          </span>
                        )}
                        <span className="font-mono text-text-dim">{m.row_key.slice(0, 12)}</span>
                      </div>
                      <p className="text-sm text-text mt-1.5 line-clamp-2">{m.question}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
