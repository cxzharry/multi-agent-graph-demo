import {Handle, Position, type Node, type NodeProps} from '@xyflow/react';

import type {RoleNode as RoleNodeData} from './types';

export type RoleFlowNode = Node<
  RoleNodeData & Record<string, unknown>,
  'role'
>;

export function RoleNode({data}: NodeProps<RoleFlowNode>) {
  const generated = data.id.startsWith('auto-');
  const showTask = !isGeneratedLaneLabel(data.id, data.task);

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
          <h3>{data.role}</h3>
          <p>Generation {data.generation}</p>
        </div>
        <span className="assignee-chip" aria-label={`Assignee ${data.assignee}`}>
          {data.assignee}
        </span>
      </div>
      {showTask && <p className="role-task">{data.task}</p>}
      <div className="role-status">
        <span>{data.status}</span>
        {!generated && <span className="role-id">{data.id}</span>}
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

function isGeneratedLaneLabel(id: string, task: string) {
  const match = /^auto-((?:[0-9a-f]{2})+)$/i.exec(id);
  if (!match) return false;

  try {
    const laneId = decodeURIComponent(
      match[1].match(/.{2}/g)!.map(byte => `%${byte}`).join(''),
    );
    return normalizeLabel(laneId) === normalizeLabel(task);
  } catch {
    return false;
  }
}

function normalizeLabel(value: string) {
  return value.toLowerCase().replace(/[\s_-]+/g, '');
}
