import { Link } from 'react-router-dom';
import { X, ExternalLink } from 'lucide-react';
import type { KnowledgeGraphNode } from '../../api/types';

interface NodeDetailPanelProps {
  courseId: string;
  node: KnowledgeGraphNode;
  nodeById: Map<string, KnowledgeGraphNode>;
  onClose: () => void;
  onSelectNode: (id: string) => void;
}

export default function NodeDetailPanel({
  courseId,
  node,
  nodeById,
  onClose,
  onSelectNode,
}: NodeDetailPanelProps) {
  const prereqNodes = node.prerequisites
    .map((id) => nodeById.get(id))
    .filter((n): n is KnowledgeGraphNode => Boolean(n));

  return (
    <aside className="card w-full lg:w-80 shrink-0 flex flex-col max-h-[70vh] overflow-hidden">
      <div className="flex items-start justify-between gap-2 p-4 border-b border-line">
        <div className="min-w-0">
          <div className="chip mb-2">Level {node.depth_level}</div>
          <h2 className="font-semibold text-text capitalize leading-snug">{node.label}</h2>
        </div>
        <button type="button" onClick={onClose} className="btn p-1.5 shrink-0" aria-label="Close">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="p-4 overflow-y-auto flex-1 space-y-4 text-sm">
        {node.description ? (
          <p className="text-text-muted leading-relaxed">{node.description}</p>
        ) : null}
        <div>
          <div className="text-xs font-medium text-text-dim uppercase tracking-wide mb-2">
            Prerequisites ({prereqNodes.length})
          </div>
          {prereqNodes.length === 0 ? (
            <p className="text-text-dim text-xs">None — root topic</p>
          ) : (
            <ul className="space-y-1">
              {prereqNodes.map((p) => (
                <li key={p.knowledge_node_id}>
                  <button
                    type="button"
                    onClick={() => onSelectNode(p.knowledge_node_id)}
                    className="text-left w-full text-brand hover:underline capitalize text-xs"
                  >
                    L{p.depth_level}: {p.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {node.source_kp_id ? (
          <Link
            to={`/courses/${courseId}/kps/${encodeURIComponent(node.source_kp_id)}`}
            className="btn w-full justify-center text-brand"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            View knowledge point
          </Link>
        ) : null}
      </div>
    </aside>
  );
}
