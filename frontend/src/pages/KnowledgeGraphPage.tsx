import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, GitBranch, Network, Sparkles } from 'lucide-react';
import CourseTabs from '../components/CourseTabs';
import SearchBox from '../components/SearchBox';
import KnowledgeGraphCanvas from '../components/knowledge-graph/KnowledgeGraphCanvas';
import NodeDetailPanel from '../components/knowledge-graph/NodeDetailPanel';
import GapExpansionPanel from '../components/knowledge-graph/GapExpansionPanel';
import { fetchCourseKnowledgeGraph } from '../api/courses';
import { depthLevelColor } from '../lib/knowledgeGraphLayout';
import type { KnowledgeGraphNode } from '../api/types';

type KgTab = 'current' | 'expansion';

export default function KnowledgeGraphPage() {
  const { courseId = '' } = useParams();
  const [kgTab, setKgTab] = useState<KgTab>('current');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hiddenLevels, setHiddenLevels] = useState<Set<number>>(new Set());

  const { data, isLoading, error } = useQuery({
    queryKey: ['knowledge-graph', courseId],
    queryFn: () => fetchCourseKnowledgeGraph(courseId),
    enabled: Boolean(courseId),
  });

  const visibleLevels = useMemo(() => {
    if (!data || hiddenLevels.size === 0) return null;
    const all = new Set(data.depth_level_definitions.map((d) => d.level));
    hiddenLevels.forEach((lv) => all.delete(lv));
    return all.size === data.depth_level_definitions.length ? null : all;
  }, [data, hiddenLevels]);

  const nodeById = useMemo(() => {
    const m = new Map<string, KnowledgeGraphNode>();
    data?.nodes.forEach((n) => m.set(n.knowledge_node_id, n));
    return m;
  }, [data]);

  const selectedNode = selectedId ? nodeById.get(selectedId) : undefined;

  const toggleLevel = (level: number) => {
    setHiddenLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  };

  if (isLoading) return <div className="text-text-muted">Loading knowledge graph…</div>;
  if (error) return <div className="text-conf-uncertain">Failed: {String(error)}</div>;
  if (!data) return <div className="text-text-muted">No knowledge graph data.</div>;

  const maxDepth = data.stats.max_depth;

  return (
    <div>
      <CourseTabs />
      <div className="flex items-center gap-2 mb-4">
        <Network className="w-5 h-5 text-brand" />
        <h1 className="text-xl font-semibold">Knowledge Graph</h1>
        <span className="text-text-muted text-sm">
          {data.stats.node_count} nodes · {data.stats.edge_count} edges · depth 0–{maxDepth}
        </span>
      </div>

      <nav className="card p-1 mb-4 inline-flex flex-wrap gap-1">
        <button
          type="button"
          onClick={() => setKgTab('current')}
          className={
            kgTab === 'current'
              ? 'inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-sm bg-brand/15 text-brand'
              : 'inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-sm text-text-muted hover:text-text hover:bg-bg-hover'
          }
        >
          <Network className="w-4 h-4" />
          Current graph
        </button>
        <button
          type="button"
          onClick={() => setKgTab('expansion')}
          title="In testing"
          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-sm relative group ${
            kgTab === 'expansion'
              ? 'bg-brand/15 text-brand'
              : 'text-text-muted hover:text-text hover:bg-bg-hover'
          }`}
        >
          <Sparkles className="w-4 h-4" />
          Gap expansion
          <AlertTriangle
            className="w-3.5 h-3.5 text-status-needs shrink-0"
            aria-label="In testing"
          />
          <span
            role="tooltip"
            className="pointer-events-none absolute left-1/2 top-full z-10 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md border border-status-needs/40 bg-bg-card px-2 py-1 text-xs text-status-needs opacity-0 shadow-md transition-opacity group-hover:opacity-100"
          >
            In testing
          </span>
        </button>
      </nav>

      {kgTab === 'expansion' ? (
        <GapExpansionPanel courseId={courseId} baselineGraph={data} />
      ) : (
        <>
          <div className="card p-4 mb-4 space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="max-w-xs flex-1">
                <SearchBox
                  value={search}
                  onChange={setSearch}
                  placeholder="Search nodes by label…"
                />
              </div>
              <button
                type="button"
                className="btn text-xs"
                onClick={() => setHiddenLevels(new Set())}
              >
                Show all levels
              </button>
            </div>
            <div>
              <div className="text-xs text-text-dim mb-2 uppercase tracking-wide font-medium">
                Depth levels — click to toggle visibility
              </div>
              <div className="flex flex-wrap gap-2">
                {data.depth_level_definitions.map((defn) => {
                  const hidden = hiddenLevels.has(defn.level);
                  const color = depthLevelColor(defn.level, maxDepth);
                  return (
                    <button
                      key={defn.level}
                      type="button"
                      onClick={() => toggleLevel(defn.level)}
                      className={hidden ? 'chip opacity-50' : 'chip-on'}
                      style={hidden ? undefined : { borderColor: color, color }}
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: color }}
                      />
                      {defn.label}
                      <span className="text-text-dim">({defn.node_count})</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 min-w-0">
              <KnowledgeGraphCanvas
                graph={data}
                visibleLevels={visibleLevels}
                searchQuery={search}
                selectedId={selectedId}
                onSelectNode={setSelectedId}
              />
              <p className="text-xs text-text-dim mt-2 flex items-center gap-1">
                <GitBranch className="w-3.5 h-3.5" />
                Arrows point from prerequisite → dependent topic. Pan and zoom to explore.
              </p>
            </div>
            {selectedNode ? (
              <NodeDetailPanel
                courseId={courseId}
                node={selectedNode}
                nodeById={nodeById}
                onClose={() => setSelectedId(null)}
                onSelectNode={setSelectedId}
              />
            ) : (
              <aside className="card w-full lg:w-80 shrink-0 p-4 text-sm text-text-muted hidden lg:block">
                Click a node to see its description, prerequisites, and link to the knowledge point
                catalog.
              </aside>
            )}
          </div>
        </>
      )}
    </div>
  );
}
