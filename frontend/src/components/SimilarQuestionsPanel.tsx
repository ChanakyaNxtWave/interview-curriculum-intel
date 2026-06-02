import { useQuery } from '@tanstack/react-query';
import { Calendar, Briefcase, Loader2 } from 'lucide-react';
import { fetchCourseGroupedQuestionMembers } from '../api/courses';

export default function SimilarQuestionsPanel({
  courseId,
  canonicalId,
  representativeRowKey,
}: {
  courseId: string;
  canonicalId: number;
  representativeRowKey: string;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['canonical-similar', courseId, canonicalId, representativeRowKey],
    queryFn: () =>
      fetchCourseGroupedQuestionMembers(
        courseId,
        canonicalId,
        200,
        representativeRowKey,
      ),
    enabled: !!courseId && !!representativeRowKey,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-xs py-2 pl-7">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-brand" />
        Loading similar questions…
      </div>
    );
  }
  if (error) {
    return (
      <div className="text-conf-uncertain text-xs py-2 pl-7">{String(error)}</div>
    );
  }

  const members = data?.members ?? [];
  if (members.length === 0) {
    return (
      <div className="text-text-dim text-xs py-2 pl-7">No other similar questions found.</div>
    );
  }

  return (
    <div className="border-t border-line bg-bg-panel/50 px-4 py-3 pl-7 space-y-2">
      <p className="text-xs text-text-dim">
        Rephrased variants or the same question from other companies (same-company repeats are
        hidden).
      </p>
      {members.map((m) => (
        <div key={m.row_key} className="rounded-md border border-line bg-bg-card p-2.5">
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-text-muted mb-1">
            {m.company_name && <span className="chip">{m.company_name}</span>}
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
          </div>
          <p className="text-sm text-text leading-snug">{m.question}</p>
        </div>
      ))}
    </div>
  );
}
