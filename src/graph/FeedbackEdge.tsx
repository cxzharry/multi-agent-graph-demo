import {BaseEdge, type Edge, type EdgeProps} from '@xyflow/react';

import {getFeedbackPath} from './layout';

export type FeedbackEdgeData = {
  feedbackGutterX: number;
  reason: string;
} & Record<string, unknown>;

export type FeedbackFlowEdge = Edge<FeedbackEdgeData, 'feedback'>;

export function FeedbackEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerEnd,
  data,
}: EdgeProps<FeedbackFlowEdge>) {
  const path = getFeedbackPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    gutterX: data?.feedbackGutterX ?? Math.max(sourceX, targetX) + 96,
  });

  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={markerEnd}
      className="feedback-edge-path"
      data-testid="feedback-edge"
      aria-label={data?.reason || 'Active failure return'}
    />
  );
}
