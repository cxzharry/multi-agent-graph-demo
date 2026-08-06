import {Handle, Position, type Node, type NodeProps} from '@xyflow/react';

import type {RoleNode as RoleNodeData} from './types';

export type RoleFlowNode = Node<
  RoleNodeData & {synthetic: boolean} & Record<string, unknown>,
  'role'
>;

export function RoleNode({data}: NodeProps<RoleFlowNode>) {
  const showTask = !data.synthetic;
  const roleLabel = data.synthetic ? compactRoleLabel(data.role) : data.role;
  const assigneeLabel = data.synthetic
    ? compactAssigneeLabel(data.role, data.assignee)
    : data.assignee;

  return (
    <article
      className={`role-node status-${data.status}${showTask ? '' : ' role-node-no-task'}`}
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
          <h3>{roleLabel}</h3>
          <p>Generation {data.generation}</p>
        </div>
        <span
          className="assignee-chip"
          aria-label={`Assignee ${data.assignee}`}
          title={data.assignee}
        >
          {assigneeLabel}
        </span>
      </div>
      {showTask && <p className="role-task">{data.task}</p>}
      <div className="role-status">
        <span>{data.status}</span>
        {!data.synthetic && <span className="role-id">{data.id}</span>}
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

export function compactRoleLabel(role: string): string {
  const match = /^p\d+[_-](.+)$/i.exec(role);
  if (!match) return role;
  return match[1]
    .split(/[_-]+/)
    .map(part =>
      ({impl: 'Implementation', qc: 'QC'} as Record<string, string>)[
        part.toLowerCase()
      ] ?? `${part.charAt(0).toUpperCase()}${part.slice(1)}`,
    )
    .join(' ');
}

export function compactAssigneeLabel(role: string, assignee: string): string {
  const position = /(?:^|\b)(p\d+)(?:[_-]|\b)/i.exec(role)?.[1];
  return position?.toUpperCase() ?? assignee;
}
