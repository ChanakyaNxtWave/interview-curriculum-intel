import { NavLink, useParams } from 'react-router-dom';
import { BookOpen, Tag, Sparkles, Code2, GitCommitVertical, Network } from 'lucide-react';

interface TabDef {
  to: string;
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
  end?: boolean;
}

export default function CourseTabs() {
  const { courseId = '' } = useParams();
  const base = `/courses/${courseId}`;
  const tabs: TabDef[] = [
    { to: base, label: 'Knowledge Points', icon: <Tag className="w-4 h-4" />, end: true },
    {
      to: `${base}/knowledge-graph`,
      label: 'Knowledge Graph',
      icon: <Network className="w-4 h-4" />,
    },
    {
      to: `${base}/reading-materials`,
      label: 'Reading Materials',
      icon: <BookOpen className="w-4 h-4" />,
    },
    {
      to: `${base}/theory-questions`,
      label: 'Theory Questions',
      icon: <Sparkles className="w-4 h-4" />,
    },
    {
      to: `${base}/coding-questions`,
      label: 'Coding Questions',
      icon: <Code2 className="w-4 h-4" />,
    },
    {
      to: `${base}/evals`,
      label: 'Evals',
      icon: <GitCommitVertical className="w-4 h-4" />,
    },
  ];
  return (
    <nav className="card p-1 inline-flex flex-wrap gap-1">
      {tabs.map((t) =>
        t.disabled ? (
          <span
            key={t.to}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm text-text-dim cursor-not-allowed"
            title="Not yet available"
          >
            {t.icon}
            {t.label}
            <span className="chip ml-1">soon</span>
          </span>
        ) : (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm ${
                isActive
                  ? 'bg-brand/15 text-brand'
                  : 'text-text-muted hover:text-text hover:bg-bg-hover'
              }`
            }
          >
            {t.icon}
            {t.label}
          </NavLink>
        ),
      )}
    </nav>
  );
}
