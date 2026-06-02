import { Link, NavLink, useLocation, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, BookOpen, GraduationCap, MessagesSquare, Inbox } from 'lucide-react';
import { fetchTheoryQuestions } from '../api/theory';

export default function Layout({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const params = useParams();
  const segments = loc.pathname.split('/').filter(Boolean);
  const reviewQ = useQuery({
    queryKey: ['review-count'],
    queryFn: () => fetchTheoryQuestions({ limit: 1 }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
  const openCount =
    (reviewQ.data?.stats?.by_status?.pending ?? 0) +
    (reviewQ.data?.stats?.by_status?.needs_review ?? 0);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line bg-bg-panel/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-screen-2xl mx-auto px-6 py-3 flex items-center gap-4 flex-wrap">
          <Link to="/" className="flex items-center gap-2 text-text font-semibold">
            <BookOpen className="w-5 h-5 text-brand" />
            <span>Curriculum Intel</span>
          </Link>
          <nav className="flex items-center gap-1">
            <NavItem to="/courses" icon={<GraduationCap className="w-4 h-4" />}>
              Courses
            </NavItem>
            <NavItem to="/interview-questions" icon={<MessagesSquare className="w-4 h-4" />}>
              Interview Questions
            </NavItem>
            <NavItem to="/review" icon={<Inbox className="w-4 h-4" />} badge={openCount}>
              Review Queue
            </NavItem>
          </nav>
          <Breadcrumbs segments={segments} params={params as Record<string, string>} />
        </div>
      </header>
      <main className="flex-1 max-w-screen-2xl w-full mx-auto px-6 py-6">{children}</main>
    </div>
  );
}

function NavItem({
  to,
  icon,
  children,
  badge,
}: {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm border ${
          isActive
            ? 'bg-brand/15 border-brand/40 text-brand'
            : 'border-transparent text-text-muted hover:text-text hover:bg-bg-hover'
        }`
      }
    >
      {icon}
      {children}
      {badge !== undefined && badge > 0 && (
        <span className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-status-needs/20 text-status-needs text-[10px] font-semibold">
          {badge}
        </span>
      )}
    </NavLink>
  );
}

function Breadcrumbs({ segments, params }: { segments: string[]; params: Record<string, string> }) {
  if (segments.length === 0) return null;
  const crumbs: { label: string; to: string }[] = [];
  let path = '';
  segments.forEach((seg, i) => {
    path += `/${seg}`;
    const next = segments[i + 1];
    let label = seg;
    if (seg === 'courses') label = 'Courses';
    else if (seg === 'knowledge-graph') label = 'Knowledge Graph';
    else if (seg === 'kps') label = 'KPs';
    else if (seg === 'content') label = 'Content';
    else if (params.courseId === seg) label = humanizeId(seg);
    else if (params.kpId === seg) label = seg;
    else if (params.contentId === seg) label = seg.slice(0, 8) + '…';
    crumbs.push({ label, to: path });
    if (next === 'kps') return;
  });
  return (
    <nav className="flex items-center gap-1 text-sm text-text-muted overflow-hidden">
      <ChevronRight className="w-3.5 h-3.5 text-text-dim shrink-0" />
      {crumbs.map((c, i) => (
        <span key={c.to} className="flex items-center gap-1 min-w-0">
          {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-text-dim shrink-0" />}
          <Link to={c.to} className="hover:text-text truncate max-w-[200px]">
            {c.label}
          </Link>
        </span>
      ))}
    </nav>
  );
}

function humanizeId(id: string) {
  return id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
