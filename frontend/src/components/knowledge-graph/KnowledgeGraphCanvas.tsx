import { useCallback, useEffect, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import KnowledgeGraphNode, { type KgNodeData } from './KnowledgeGraphNode';
import { depthLevelColor, layoutKnowledgeGraph } from '../../lib/knowledgeGraphLayout';
import type { KnowledgeGraphNode as KgNode, KnowledgeGraphResponse } from '../../api/types';

const nodeTypes = { kgNode: KnowledgeGraphNode };

interface KnowledgeGraphCanvasProps {
  graph: KnowledgeGraphResponse;
  visibleLevels: Set<number> | null;
  searchQuery: string;
  selectedId: string | null;
  onSelectNode: (id: string | null) => void;
}

function buildFlowElements(
  graph: KnowledgeGraphResponse,
  visibleLevels: Set<number> | null,
  searchQuery: string,
  selectedId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const q = searchQuery.trim().toLowerCase();
  const maxDepth = graph.stats.max_depth;
  const visibleIds = new Set<string>();

  for (const n of graph.nodes) {
    if (visibleLevels && !visibleLevels.has(n.depth_level)) continue;
    visibleIds.add(n.knowledge_node_id);
  }

  const nodes: Node[] = graph.nodes
    .filter((n) => visibleIds.has(n.knowledge_node_id))
    .map((n: KgNode) => {
      const matchesSearch = !q || n.label.toLowerCase().includes(q);
      return {
        id: n.knowledge_node_id,
        type: 'kgNode',
        position: { x: 0, y: 0 },
        data: {
          label: n.label,
          depthLevel: n.depth_level,
          color:
            n.origin === 'proposed'
              ? '#f59e0b'
              : depthLevelColor(n.depth_level, maxDepth),
          dimmed: Boolean(q && !matchesSearch),
          highlighted: selectedId === n.knowledge_node_id,
          isProposed: n.origin === 'proposed',
          touchCount: n.touch_count,
        } satisfies KgNodeData,
      };
    });

  const edges: Edge[] = graph.edges
    .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
    .map((e, i) => ({
      id: `e-${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      animated: false,
      style: { stroke: '#4a5568', strokeWidth: 1.5 },
    }));

  const layouted = layoutKnowledgeGraph(nodes, edges);
  return { nodes: layouted, edges };
}

export default function KnowledgeGraphCanvas({
  graph,
  visibleLevels,
  searchQuery,
  selectedId,
  onSelectNode,
}: KnowledgeGraphCanvasProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildFlowElements(graph, visibleLevels, searchQuery, selectedId),
    [graph, visibleLevels, searchQuery, selectedId],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    const { nodes: n, edges: e } = buildFlowElements(
      graph,
      visibleLevels,
      searchQuery,
      selectedId,
    );
    setNodes(n);
    setEdges(e);
  }, [graph, visibleLevels, searchQuery, selectedId, setNodes, setEdges]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      onSelectNode(node.id);
    },
    [onSelectNode],
  );

  const onPaneClick = useCallback(() => {
    onSelectNode(null);
  }, [onSelectNode]);

  return (
    <div className="h-[70vh] w-full rounded-lg border border-line overflow-hidden bg-bg-panel">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.08}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="#2a2f3f" />
        <Controls className="!bg-bg-card !border-line !shadow-md [&>button]:!bg-bg-panel [&>button]:!border-line [&>button]:!text-text [&>button:hover]:!bg-bg-hover" />
        <MiniMap
          className="!bg-bg-card !border-line"
          nodeColor={(n) => (n.data as KgNodeData).color}
          maskColor="rgba(0,0,0,0.55)"
        />
      </ReactFlow>
    </div>
  );
}
