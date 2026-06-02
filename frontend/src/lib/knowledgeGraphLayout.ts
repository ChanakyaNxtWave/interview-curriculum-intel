import dagre from 'dagre';
import { Position, type Edge, type Node } from '@xyflow/react';

const NODE_WIDTH = 220;
const NODE_HEIGHT = 56;

export function depthLevelColor(level: number, maxDepth: number): string {
  if (maxDepth <= 0) return 'hsl(220, 70%, 55%)';
  const t = level / maxDepth;
  const hue = 210 - t * 180;
  return `hsl(${hue}, 65%, 48%)`;
}

export function layoutKnowledgeGraph(
  nodes: Node[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'TB',
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 28, ranksep: 72, marginx: 24, marginy: 24 });

  nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
      sourcePosition: direction === 'TB' ? Position.Bottom : Position.Right,
      targetPosition: direction === 'TB' ? Position.Top : Position.Left,
    };
  });
}
