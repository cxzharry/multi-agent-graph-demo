import {Handle, Position, type Node, type NodeProps} from '@xyflow/react';

import type {RoleNode as RoleNodeData} from './types';

export type RoleFlowNode = Node<
  RoleNodeData & Record<string, unknown>,
  'role'
>;

export function RoleNode({data}: NodeProps<RoleFlowNode>) {
  return (
    <article
      className={`role-node status-${data.status}`}
      data-node-id={data.id}
      data-status={data.status}
      data-testid="role-node"
    >
      <Handle
        className="role-handle"
        isConnectable={false}
        position={Position.Top}
        type="target"
      />
      <div className="role-node-heading">
        <span className="status-dot" aria-hidden="true" />
        <div>
          <h3>{data.role}</h3>
          <p>Generation {data.generation}</p>
        </div>
        <span className="assignee-chip">{data.assignee}</span>
      </div>
      <p className="role-task">{data.task}</p>
      <div className="role-status">
        <span>{data.status}</span>
        <span className="role-id">{data.id}</span>
      </div>
      <Handle
        className="role-handle"
        isConnectable={false}
        position={Position.Bottom}
        type="source"
      />
    </article>
  );
}
