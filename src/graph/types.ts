export type NodeStatus =
  | 'pending'
  | 'running'
  | 'passed'
  | 'failed'
  | 'blocked'
  | 'retrying'
  | 'stale'
  | 'skipped';

export type AgentLiveness = 'running' | 'idle' | 'offline' | 'stale';

export type AssignmentResult =
  | 'pass'
  | 'fail'
  | 'blocked'
  | 'skipped'
  | 'rework';

export type RelationshipMode = 'declared' | 'event-backed' | 'unavailable';

export type EdgeKind = 'forward' | 'return' | 'control';

export type EdgeStatus =
  | 'pending'
  | 'active'
  | 'inactive'
  | 'passed'
  | 'failed'
  | 'blocked'
  | 'retrying'
  | 'stale'
  | 'skipped';

export type RoleNode = {
  id: string;
  role: string;
  assignee: string;
  layer?: number;
  status: NodeStatus;
  liveness?: AgentLiveness;
  result?: AssignmentResult;
  lastActivityAt?: string;
  task: string;
  generation: number;
};

export type RoleEdge = {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  status: EdgeStatus;
  occurrenceCount?: number;
  lastEventAt?: string;
  reason?: string;
};

export type FailurePolicy = {
  gateNodeId: string;
  returnToNodeId: string;
  ownerNodeId: string;
  resumeNodeId: string;
  rerunNodeIds: string[];
  excludedNodeIds: string[];
};

export type ActiveFailureRoute = FailurePolicy & {
  reason: string;
  generation: number;
};

export type GraphEvent = Record<string, unknown>;

export type RoleGraphSnapshot = {
  schemaVersion: 'role-graph/v1';
  flowId?: string;
  spaceName?: string;
  shortName?: string;
  scopeId: string;
  runId: string;
  sequence: number;
  generatedAt: string;
  title: string;
  relationshipMode?: RelationshipMode;
  nodes: RoleNode[];
  edges: RoleEdge[];
  failurePolicies: FailurePolicy[];
  activeFailureRoute: ActiveFailureRoute | null;
  events: GraphEvent[];
};

export type GraphSummary = Pick<
  RoleGraphSnapshot,
  'spaceName' | 'scopeId' | 'runId' | 'sequence' | 'generatedAt' | 'title'
> & {
  shortName: string;
  isLive: boolean;
  runStatus: 'RUNNING' | 'DONE' | 'FAILED' | 'PENDING';
};

export type GraphSelection = Pick<RoleGraphSnapshot, 'scopeId' | 'runId'>;
