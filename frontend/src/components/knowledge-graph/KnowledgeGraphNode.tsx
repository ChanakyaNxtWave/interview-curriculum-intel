import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';

export type KgNodeData = {
  label: string;
  depthLevel: number;
  color: string;
  dimmed?: boolean;
  highlighted?: boolean;
  isProposed?: boolean;
  touchCount?: number;
};

function KnowledgeGraphNodeComponent({ data }: NodeProps) {
  const d = data as KgNodeData;
  return (
    <div
      className={`px-2.5 py-2 rounded-md border-2 shadow-sm min-w-[180px] max-w-[220px] transition-opacity ${
        d.isProposed ? 'bg-status-needs/10' : 'bg-bg-card'
      } ${d.dimmed ? 'opacity-25' : 'opacity-100'} ${
        d.highlighted ? 'ring-2 ring-brand ring-offset-1 ring-offset-bg' : ''
      }`}
      style={{ borderColor: d.isProposed ? '#f59e0b' : d.color }}
    >
      <Handle type="target" position={Position.Top} className="!bg-text-dim !w-2 !h-2" />
      <div className="text-[10px] font-medium uppercase tracking-wide text-text-dim mb-0.5 flex items-center justify-between gap-1">
        <span>{d.isProposed ? 'Proposed' : `Level ${d.depthLevel}`}</span>
        {d.isProposed && d.touchCount != null && d.touchCount > 0 && (
          <span className="text-status-needs normal-case">{d.touchCount}×</span>
        )}
      </div>
      <div className="text-xs font-medium text-text leading-snug line-clamp-2 capitalize">
        {d.label}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-text-dim !w-2 !h-2" />
    </div>
  );
}

export default memo(KnowledgeGraphNodeComponent);
