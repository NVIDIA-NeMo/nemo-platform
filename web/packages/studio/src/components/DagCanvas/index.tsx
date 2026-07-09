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
  useNodesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { type FC, useEffect, useMemo, useRef } from 'react';

const NODE_TYPES = { card: CardNode };

/** Stable id for an edge; falls back to a source/target pair when none is given. */
const edgeId = (edge: DagEdge): string => edge.id ?? `${edge.source}->${edge.target}`;

export interface DagCanvasProps {
  /** Graph nodes; positions are computed automatically. */
  nodes: DagNode[];
  /** Directed edges between nodes, drawn as arrows. */
  edges: DagEdge[];
  /** Fired with the node id and its data when a card is clicked or keyboard-activated. */
  onNodeClick?: (id: string, data: DagNodeData) => void;
  /** Layout flow direction; defaults to `'TB'` (top-to-bottom). */
  direction?: DagDirection;
  /**
   * Light/dark mode for the canvas. Defaults to following the Studio theme (the
   * `nv-dark` class on `<html>`). Set explicitly to override.
   */
  colorMode?: ColorMode;
  className?: string;
}

/**
 * A pan-and-zoom canvas that renders a DAG of clickable card nodes connected by
 * arrows. Nodes are auto-laid-out top-down (or left-right) with dagre, so callers
 * supply only `nodes` and `edges` — no coordinates. The canvas pans on drag and
 * zooms on scroll/pinch; nodes are fixed in their computed layout (not draggable).
 *
 * The host element must have a defined size (e.g. `h-full w-full` inside a sized
 * parent); React Flow fills its container.
 */
export const DagCanvas: FC<DagCanvasProps> = ({
  nodes,
  edges,
  onNodeClick,
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
    const rfNodes: CardNodeType[] = nodes.map((node) => ({
      id: node.id,
      type: 'card',
      position: { x: 0, y: 0 },
      data: { ...node.data, onActivate: () => onNodeClickRef.current?.(node.id, node.data) },
    }));
    const rfEdges: Edge[] = edges.map((edge) => ({
      id: edgeId(edge),
      source: edge.source,
      target: edge.target,
      // Pass the label through so dagre can reserve space for it during layout.
      label: edge.label,
    }));
    return layoutGraph(rfNodes, rfEdges, direction);
  }, [nodes, edges, direction]);

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
        nodesDraggable={false}
        fitView
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
};
