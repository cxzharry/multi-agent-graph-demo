export type NodeStatus =
  | 'pending'
  | 'running'
  | 'passed'
  | 'failed'
  | 'blocked'
  | 'retrying'
  | 'stale'
  | 'skipped';

export type EdgeKind = 'forward' | 'return';

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
  task: string;
  generation: number;
};

export type RoleEdge = {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  status: EdgeStatus;
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
  scopeId: string;
  runId: string;
  sequence: number;
  generatedAt: string;
  title: string;
  nodes: RoleNode[];
  edges: RoleEdge[];
  failurePolicies: FailurePolicy[];
  activeFailureRoute: ActiveFailureRoute | null;
  events: GraphEvent[];
};

export type GraphSummary = Pick<
  RoleGraphSnapshot,
  'scopeId' | 'runId' | 'sequence' | 'generatedAt' | 'title'
>;

export type GraphSelection = Pick<RoleGraphSnapshot, 'scopeId' | 'runId'>;
