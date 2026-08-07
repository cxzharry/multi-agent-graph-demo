import {Handle, Position, type Node, type NodeProps} from '@xyflow/react';

import type {AgentLiveness, RoleNode as RoleNodeData} from './types';

export type RoleFlowNode = Node<
  RoleNodeData & {synthetic: boolean} & Record<string, unknown>,
  'role'
>;

export function RoleNode({data}: NodeProps<RoleFlowNode>) {
  const showTask = !data.synthetic;
  const liveness = data.liveness ?? legacyLiveness(data.status);
  const hasLiveFacts = data.liveness !== undefined;
  const roleLabel = data.synthetic ? compactRoleLabel(data.role) : data.role;
  const assigneeLabel = data.synthetic
    ? compactAssigneeLabel(data.role, data.assignee)
    : data.assignee;

  return (
    <article
      className={`role-node status-${data.status} liveness-${liveness}${hasLiveFacts ? ' has-live-facts' : ''}${showTask ? '' : ' role-node-no-task'}`}
      data-node-id={data.id}
      data-liveness={liveness}
      data-result={data.result}
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
          <h3 aria-label={`Role ${data.role}`} title={data.role}>
            {roleLabel}
          </h3>
          <p>Generation {data.generation}</p>
        </div>
        <span
          className={`assignee-chip${/^P[1-9]$/.test(assigneeLabel) ? '' : ' assignee-chip-non-position'}`}
          aria-label={`Assignee ${data.assignee}`}
          title={data.assignee}
        >
          {assigneeLabel}
        </span>
      </div>
      {showTask && <p className="role-task">{data.task}</p>}
      <div className="role-status">
        {hasLiveFacts ? (
          <div className="role-badges">
            <span className={`liveness-badge liveness-badge-${liveness}`}>
              {liveness.toUpperCase()}
            </span>
            {data.result && (
              <span className={`result-badge result-badge-${data.result}`}>
                {data.result.toUpperCase()}
              </span>
            )}
          </div>
        ) : (
          <span>{data.status}</span>
        )}
        {data.lastActivityAt && (
          <time
            className="activity-time"
            dateTime={data.lastActivityAt}
            title={data.lastActivityAt}
          >
            {relativeActivity(data.lastActivityAt)}
          </time>
        )}
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

function legacyLiveness(status: RoleNodeData['status']): AgentLiveness {
  if (status === 'running' || status === 'retrying') return 'running';
  if (status === 'blocked' || status === 'stale') return 'stale';
  if (status === 'pending') return 'idle';
  return 'offline';
}

function relativeActivity(value: string): string {
  const elapsed = Math.max(0, Date.now() - Date.parse(value));
  if (elapsed < 60_000) return 'just now';
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}m ago`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}h ago`;
  return `${Math.floor(elapsed / 86_400_000)}d ago`;
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
