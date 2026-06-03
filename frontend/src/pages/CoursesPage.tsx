import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { BookOpen, GraduationCap, Tag, Files, CheckCircle2, Layers, Network } from 'lucide-react';
import { fetchCourses } from '../api/courses';
import StickyPageChrome from '../components/StickyPageChrome';

export default function CoursesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ['courses'], queryFn: fetchCourses });

  if (isLoading) return <div className="text-text-muted">Loading courses…</div>;
  if (error) return <div className="text-conf-uncertain">Failed: {String(error)}</div>;
  if (!data?.courses?.length)
    return <div className="text-text-muted">No courses found.</div>;

  return (
    <div>
      <StickyPageChrome>
        <div className="flex items-center gap-2">
          <GraduationCap className="w-5 h-5 text-brand" />
          <h1 className="text-xl font-semibold">Courses</h1>
          <span className="text-text-muted text-sm">({data.courses.length})</span>
        </div>
      </StickyPageChrome>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.courses.map((c) => (
          <div key={c.course_id} className="card p-5 hover:bg-bg-hover hover:border-brand/40 transition-colors group">
            <Link to={`/courses/${c.course_id}`} className="block">
              <div className="flex items-start gap-3">
                <BookOpen className="w-6 h-6 text-brand mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-text group-hover:text-brand truncate">
                    {c.course_title}
                  </div>
                  <div className="text-xs text-text-dim mt-0.5">{c.course_id}</div>
                </div>
              </div>
              <div
                className={`mt-4 grid gap-2 text-sm ${
                  c.has_knowledge_graph ? 'grid-cols-5' : 'grid-cols-4'
                }`}
              >
                <Stat icon={<Tag className="w-3.5 h-3.5" />} label="KPs" value={c.kp_count} />
                <Stat icon={<Files className="w-3.5 h-3.5" />} label="Content" value={c.content_count} />
                <Stat
                  icon={<CheckCircle2 className="w-3.5 h-3.5" />}
                  label="Mapped"
                  value={c.mapped_count}
                />
                <Stat
                  icon={<Layers className="w-3.5 h-3.5" />}
                  label="Grouped Qs"
                  value={c.grouped_question_count ?? 0}
                />
                {c.has_knowledge_graph ? (
                  <Stat
                    icon={<Network className="w-3.5 h-3.5" />}
                    label="Graph"
                    value={c.knowledge_graph_node_count ?? 0}
                  />
                ) : null}
              </div>
            </Link>
            {c.has_knowledge_graph ? (
              <Link
                to={`/courses/${c.course_id}/knowledge-graph`}
                className="mt-3 inline-flex items-center gap-1.5 text-sm text-brand hover:underline"
              >
                <Network className="w-3.5 h-3.5" />
                View knowledge graph
              </Link>
            ) : null}
          </div>
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
