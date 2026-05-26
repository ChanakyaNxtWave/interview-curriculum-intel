import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { BookOpen, GraduationCap, Tag, Files, CheckCircle2 } from 'lucide-react';
import { fetchCourses } from '../api/courses';

export default function CoursesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ['courses'], queryFn: fetchCourses });

  if (isLoading) return <div className="text-text-muted">Loading courses…</div>;
  if (error) return <div className="text-conf-uncertain">Failed: {String(error)}</div>;
  if (!data?.courses?.length)
    return <div className="text-text-muted">No courses found.</div>;

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <GraduationCap className="w-5 h-5 text-brand" />
        <h1 className="text-xl font-semibold">Courses</h1>
        <span className="text-text-muted text-sm">({data.courses.length})</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.courses.map((c) => (
          <Link
            key={c.course_id}
            to={`/courses/${c.course_id}`}
            className="card p-5 hover:bg-bg-hover hover:border-brand/40 transition-colors group"
          >
            <div className="flex items-start gap-3">
              <BookOpen className="w-6 h-6 text-brand mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-text group-hover:text-brand truncate">
                  {c.course_title}
                </div>
                <div className="text-xs text-text-dim mt-0.5">{c.course_id}</div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <Stat icon={<Tag className="w-3.5 h-3.5" />} label="KPs" value={c.kp_count} />
              <Stat icon={<Files className="w-3.5 h-3.5" />} label="Content" value={c.content_count} />
              <Stat
                icon={<CheckCircle2 className="w-3.5 h-3.5" />}
                label="Mapped"
                value={c.mapped_count}
              />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="bg-bg-panel border border-line rounded-md px-2 py-1.5">
      <div className="flex items-center gap-1 text-text-dim text-xs">
        {icon}
        <span>{label}</span>
      </div>
      <div className="text-text font-medium tabular-nums">{value}</div>
    </div>
  );
}
