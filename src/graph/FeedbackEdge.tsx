import {
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react';

import {getFeedbackPath} from './layout';

export type FeedbackEdgeData = {
  feedbackGutterX: number;
  label?: string;
  labelTitle?: string;
  muted?: boolean;
  reason: string;
} & Record<string, unknown>;

export type RelationshipEdgeData = {
  label?: string;
  labelOffsetX?: number;
  labelOffsetY?: number;
  labelProgress?: number;
  labelTitle?: string;
  muted?: boolean;
} & Record<string, unknown>;

export type FeedbackFlowEdge = Edge<FeedbackEdgeData, 'feedback'>;
export type RelationshipFlowEdge = Edge<
  RelationshipEdgeData,
  'relationship'
>;

export function FeedbackEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerEnd,
  data,
}: EdgeProps<FeedbackFlowEdge>) {
  const gutterX =
    data?.feedbackGutterX ?? Math.max(sourceX, targetX) + 96;
  const path = getFeedbackPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    gutterX,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className="feedback-edge-path"
        data-testid="feedback-edge"
        aria-label={data?.labelTitle || data?.reason || 'Active failure return'}
      />
      {data?.label && (
        <RelationshipLabel
          edgeId={id}
          label={data.label}
          title={data.labelTitle}
          x={sourceX + (gutterX - sourceX) * 0.28}
          y={sourceY + 18}
          muted={data.muted}
        />
      )}
    </>
  );
}

export function RelationshipEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerEnd,
  data,
}: EdgeProps<RelationshipFlowEdge>) {
  const [path] = getStraightPath({sourceX, sourceY, targetX, targetY});
  const verticalDistance = Math.abs(targetY - sourceY);
  const progress =
    data?.labelProgress ?? Math.min(0.3, 22 / Math.max(verticalDistance, 1));

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className="relationship-edge-path"
        aria-label={data?.labelTitle || data?.label || 'Workflow relationship'}
      />
      {data?.label && (
        <RelationshipLabel
          edgeId={id}
          label={data.label}
          title={data.labelTitle}
          x={
            sourceX +
            (targetX - sourceX) * progress +
            (data.labelOffsetX ?? 0)
          }
          y={
            sourceY +
            (targetY - sourceY) * progress +
            (data.labelOffsetY ?? 0)
          }
          muted={data.muted}
        />
      )}
    </>
  );
}

function RelationshipLabel({
  edgeId,
  label,
  title,
  x,
  y,
  muted,
}: {
  edgeId: string;
  label: string;
  title?: string;
  x: number;
  y: number;
  muted?: boolean;
}) {
  return (
    <EdgeLabelRenderer>
      <span
        className={`relationship-edge-label${muted ? ' relationship-edge-label-muted' : ''}`}
        data-edge-id={edgeId}
        data-testid="relationship-label"
        title={title}
        style={{
          transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
        }}
      >
        {label}
      </span>
    </EdgeLabelRenderer>
  );
}
