// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CardNode, type CardNodeType } from '@studio/components/DagCanvas/CardNode';
import { layoutGraph } from '@studio/components/DagCanvas/layout';
import type {
  DagDirection,
  DagEdge,
  DagNode,
  DagNodeData,
} from '@studio/components/DagCanvas/types';
import { useNvColorMode } from '@studio/components/DagCanvas/useNvColorMode';
import {
  Background,
  type ColorMode,
  Controls,
  type Edge,
  MarkerType,
  ReactFlow,
  useEdgesState,
  useNodes,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { type FC, useEffect, useMemo, useRef } from 'react';

const NODE_TYPES = { card: CardNode };

/** Stable id for an edge; falls back to a source/target pair when none is given. */
const edgeId = (edge: DagEdge): string => edge.id ?? `${edge.source}->${edge.target}`;
/**
 * Pans/zooms the viewport to center `focusNodeId` whenever it changes to a node present
 * on the canvas. Rendered inside `ReactFlow` so it can use the flow hooks. Tracks the
 * last-focused id so live edits to a focused node don't re-center it, and defers focus
 * until a just-added node has actually landed in the store.
 */
const FocusController: FC<{ focusNodeId?: string | null }> = ({ focusNodeId }) => {
  const { fitView } = useReactFlow();
  const nodes = useNodes();
  const lastFocused = useRef<string | null>(null);

  useEffect(() => {
    if (!focusNodeId || focusNodeId === lastFocused.current) return;
    if (!nodes.some((node) => node.id === focusNodeId)) return;
    lastFocused.current = focusNodeId;
    fitView({ nodes: [{ id: focusNodeId }], duration: 500, padding: 0.4, maxZoom: 1.2 });
  }, [focusNodeId, nodes, fitView]);

  return null;
};

export interface DagCanvasProps {
  /** Graph nodes; positions are computed automatically. */
  nodes: DagNode[];
  edges: DagEdge[];
  onNodeClick?: (id: string, data: DagNodeData) => void;
  /** When set (or changed), the viewport animates to center this node. */
  focusNodeId?: string | null;
  /** Fired for each node removed via the canvas (e.g. Backspace on a selected node). */
  onNodeDelete?: (id: string) => void;
  /** Layout flow direction; defaults to `'TB'` (top-to-bottom). */
  direction?: DagDirection;
  /**
   * Light/dark mode for the canvas. Defaults to following the Studio theme (the
   * `nv-dark` class on `<html>`). Set explicitly to override.
   */
  colorMode?: ColorMode;
  className?: string;
}

/** The host element must have a defined size (e.g. `h-full w-full` inside a sized parent); React Flow fills its container. */
export const DagCanvas: FC<DagCanvasProps> = ({
  nodes,
  edges,
  onNodeClick,
  focusNodeId,
  onNodeDelete,
  direction = 'TB',
  colorMode,
  className,
}) => {
  const themeColorMode = useNvColorMode();
  const onNodeClickRef = useRef(onNodeClick);
  useEffect(() => {
    onNodeClickRef.current = onNodeClick;
  }, [onNodeClick]);

  const laidOutNodes = useMemo<CardNodeType[]>(() => {
    // A node only shows the handle for a side that actually has an edge, so
    // fully-unconnected nodes render no handles.
    const targets = new Set(edges.map((edge) => edge.target));
    const sources = new Set(edges.map((edge) => edge.source));
    const rfNodes: CardNodeType[] = nodes.map((node) => ({
      id: node.id,
      type: 'card',
      position: { x: 0, y: 0 },
      data: {
        ...node.data,
        onActivate: () => onNodeClick?.(node.id, node.data),
        hasIncoming: targets.has(node.id),
        hasOutgoing: sources.has(node.id),
      },
    }));
    const rfEdges: Edge[] = edges.map((edge) => ({
      id: edgeId(edge),
      source: edge.source,
      target: edge.target,
      // Pass the label through so dagre can reserve space for it during layout.
      label: edge.label,
    }));
    return layoutGraph(rfNodes, rfEdges, direction);
  }, [edges, nodes, direction, onNodeClick]);

  const styledEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        id: edgeId(edge),
        source: edge.source,
        target: edge.target,
        label: edge.label,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
    [edges]
  );

  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState(laidOutNodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(styledEdges);

  // Re-sync internal React Flow state when the input graph (or layout) changes.
  useEffect(() => setFlowNodes(laidOutNodes), [laidOutNodes, setFlowNodes]);
  useEffect(() => setFlowEdges(styledEdges), [styledEdges, setFlowEdges]);

  return (
    <div className={`size-full bg-surface-sunken ${className ?? ''}`}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={NODE_TYPES}
        colorMode={colorMode ?? themeColorMode}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodesDelete={(deleted) => deleted.forEach((node) => onNodeDelete?.(node.id))}
        nodesDraggable={false}
        fitView
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
        <FocusController focusNodeId={focusNodeId} />
      </ReactFlow>
    </div>
  );
};
