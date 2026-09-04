// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CardNode, type CardNodeType } from '@studio/components/DagCanvas/CardNode';
import { layoutGraph } from '@studio/components/DagCanvas/layout';
import { getGraphMotionDuration } from '@studio/components/DagCanvas/motion';
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
  type NodeChange,
  ReactFlow,
  type Viewport,
  useEdgesState,
  useNodes,
  useNodesInitialized,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import '@studio/components/DagCanvas/DagCanvas.css';
import '@xyflow/react/dist/style.css';
import { type FC, useCallback, useEffect, useMemo, useRef } from 'react';

const NODE_TYPES = { card: CardNode };
const MIN_GRAPH_ZOOM = 0.001;

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
    fitView({
      nodes: [{ id: focusNodeId }],
      duration: getGraphMotionDuration(),
      padding: 0.4,
      maxZoom: 1.2,
    });
  }, [focusNodeId, nodes, fitView]);

  return null;
};

const CenterNodeController: FC<{
  centerNodeId?: string | null;
  requestNonce?: number;
}> = ({ centerNodeId, requestNonce }) => {
  const { getNodesBounds, getZoom, setCenter } = useReactFlow();
  const nodes = useNodes();
  const lastRequest = useRef('');

  useEffect(() => {
    if (!centerNodeId || requestNonce === undefined) return;
    const request = `${centerNodeId}:${requestNonce}`;
    if (request === lastRequest.current || !nodes.some(({ id }) => id === centerNodeId)) return;
    const bounds = getNodesBounds([centerNodeId]);
    const zoom = getZoom();
    if (
      ![bounds.x, bounds.y, bounds.width, bounds.height, zoom].every(Number.isFinite) ||
      bounds.width <= 0 ||
      bounds.height <= 0
    ) {
      return;
    }
    lastRequest.current = request;
    setCenter(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2, {
      zoom,
      duration: getGraphMotionDuration(),
    });
  }, [centerNodeId, getNodesBounds, getZoom, nodes, requestNonce, setCenter]);

  return null;
};

const readViewport = (key: string): Viewport | null => {
  try {
    const viewport = JSON.parse(sessionStorage.getItem(key) ?? '') as Partial<Viewport>;
    return typeof viewport.x === 'number' &&
      typeof viewport.y === 'number' &&
      typeof viewport.zoom === 'number'
      ? (viewport as Viewport)
      : null;
  } catch {
    return null;
  }
};

const FitGraphController: FC<{
  viewportStorageKey?: string;
  selectedNodeId?: string | null;
}> = ({ viewportStorageKey, selectedNodeId }) => {
  const { fitView } = useReactFlow();
  const nodes = useNodes();
  const nodesInitialized = useNodesInitialized();
  const graphId = nodes.map((node) => node.id).join('|');
  const lastFittedGraph = useRef<string | null>(null);

  useEffect(() => {
    if (!nodesInitialized || !graphId) return;
    if (lastFittedGraph.current === null) {
      lastFittedGraph.current = graphId;
      return;
    }
    if (graphId === lastFittedGraph.current) return;
    lastFittedGraph.current = graphId;
    requestAnimationFrame(() => {
      const savedViewport = viewportStorageKey ? readViewport(viewportStorageKey) : null;
      const savedZoom = savedViewport
        ? Math.min(Math.max(savedViewport.zoom, MIN_GRAPH_ZOOM), 2)
        : null;
      const selectedNode = selectedNodeId && nodes.some(({ id }) => id === selectedNodeId);
      fitView({
        nodes: selectedNode ? [{ id: selectedNodeId }] : undefined,
        padding: 0.12,
        minZoom: savedZoom ?? MIN_GRAPH_ZOOM,
        maxZoom: savedZoom ?? 1,
      });
    });
  }, [fitView, graphId, nodes, nodesInitialized, selectedNodeId, viewportStorageKey]);

  return null;
};

const FitNodesController: FC<{ nodeIds?: readonly string[] }> = ({ nodeIds }) => {
  const { fitView } = useReactFlow();
  const nodes = useNodes();
  const fitKey = nodeIds?.join('|') ?? '';
  const lastFitKey = useRef('');

  useEffect(() => {
    if (!fitKey) {
      lastFitKey.current = '';
      return;
    }
    if (fitKey === lastFitKey.current) return;
    const visibleNodes = nodes.filter(({ id }) => nodeIds?.includes(id));
    if (visibleNodes.length !== nodeIds?.length) return;
    lastFitKey.current = fitKey;
    requestAnimationFrame(() => {
      fitView({
        nodes: visibleNodes.map(({ id }) => ({ id })),
        duration: getGraphMotionDuration(),
        padding: 0.18,
        minZoom: MIN_GRAPH_ZOOM,
        maxZoom: 1,
      });
    });
  }, [fitKey, fitView, nodeIds, nodes]);

  return null;
};

export interface DagCanvasProps {
  /** Graph nodes; positions are computed automatically. */
  nodes: DagNode[];
  edges: DagEdge[];
  onNodeClick?: (id: string, data: DagNodeData) => void;
  /** Node shown as selected without moving the viewport. */
  selectedNodeId?: string | null;
  /** When set (or changed), the viewport animates to center this node. */
  focusNodeId?: string | null;
  /** When set, the viewport animates to include all listed nodes. */
  fitNodeIds?: readonly string[];
  /** When requested, the viewport centers this node without changing zoom. */
  centerNodeId?: string | null;
  centerNodeNonce?: number;
  /** Fired for each node removed via the canvas (e.g. Backspace on a selected node). */
  onNodeDelete?: (id: string) => void;
  /** Layout flow direction; defaults to `'TB'` (top-to-bottom). */
  direction?: DagDirection;
  /**
   * Light/dark mode for the canvas. Defaults to following the Studio theme (the
   * `nv-dark` class on `<html>`). Set explicitly to override.
   */
  colorMode?: ColorMode;
  /** Session storage key used to retain the user's viewport when the canvas remounts. */
  viewportStorageKey?: string;
  className?: string;
}

/** The host element must have a defined size (e.g. `h-full w-full` inside a sized parent); React Flow fills its container. */
export const DagCanvas: FC<DagCanvasProps> = ({
  nodes,
  edges,
  onNodeClick,
  selectedNodeId,
  focusNodeId,
  fitNodeIds,
  centerNodeId,
  centerNodeNonce,
  onNodeDelete,
  direction = 'TB',
  colorMode,
  viewportStorageKey,
  className,
}) => {
  const themeColorMode = useNvColorMode();
  const initialViewport = useMemo(
    () => (viewportStorageKey ? readViewport(viewportStorageKey) : null),
    [viewportStorageKey]
  );
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
      selected: false,
      data: {
        ...node.data,
        onActivate: () => onNodeClickRef.current?.(node.id, node.data),
        hasIncoming: targets.has(node.id),
        hasOutgoing: sources.has(node.id),
        stopPropagation: !onNodeDelete,
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
  }, [edges, nodes, direction, onNodeDelete]);

  const renderedNodes = useMemo<CardNodeType[]>(
    () =>
      laidOutNodes.map((node) => ({
        ...node,
        deletable: Boolean(onNodeDelete),
        selected: node.id === selectedNodeId,
      })),
    [laidOutNodes, onNodeDelete, selectedNodeId]
  );

  const styledEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        id: edgeId(edge),
        source: edge.source,
        target: edge.target,
        label: edge.label,
        type: 'smoothstep',
        markerEnd: {
          type: MarkerType.ArrowClosed,
          ...(edge.highlighted ? { color: 'var(--border-color-brand)' } : undefined),
        },
        className: edge.highlighted ? 'nemo-dag-path-edge' : undefined,
        deletable: false,
        animated: false,
        style: edge.highlighted
          ? { stroke: 'var(--border-color-brand)', strokeWidth: 2.5 }
          : edge.muted
            ? { opacity: 0.2 }
            : undefined,
      })),
    [edges]
  );

  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState(renderedNodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(styledEdges);

  // Re-sync internal React Flow state when the input graph (or layout) changes.
  useEffect(() => setFlowNodes(renderedNodes), [renderedNodes, setFlowNodes]);
  useEffect(() => setFlowEdges(styledEdges), [styledEdges, setFlowEdges]);
  const handleMoveEnd = useCallback(
    (_: MouseEvent | TouchEvent | null, viewport: Viewport) => {
      if (!viewportStorageKey) return;
      try {
        sessionStorage.setItem(viewportStorageKey, JSON.stringify(viewport));
      } catch {
        // Storage can be unavailable in privacy-restricted browser contexts.
      }
    },
    [viewportStorageKey]
  );
  const handleNodesChange = useCallback(
    (changes: NodeChange<CardNodeType>[]) =>
      onNodesChange(onNodeDelete ? changes : changes.filter((change) => change.type !== 'select')),
    [onNodeDelete, onNodesChange]
  );

  return (
    <div className={`size-full bg-surface-sunken ${className ?? ''}`}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={NODE_TYPES}
        colorMode={colorMode ?? themeColorMode}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        onMoveEnd={handleMoveEnd}
        onNodesDelete={(deleted) => deleted.forEach((node) => onNodeDelete?.(node.id))}
        nodesDraggable={false}
        nodesFocusable={Boolean(onNodeDelete)}
        edgesFocusable={false}
        elevateNodesOnSelect={false}
        fitViewOptions={{ padding: 0.12, minZoom: MIN_GRAPH_ZOOM, maxZoom: 1 }}
        minZoom={MIN_GRAPH_ZOOM}
        maxZoom={2}
        onlyRenderVisibleElements={flowNodes.length > 250}
        defaultViewport={initialViewport ?? undefined}
        fitView={!initialViewport}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls position="top-left" />
        <FitGraphController
          viewportStorageKey={viewportStorageKey}
          selectedNodeId={selectedNodeId}
        />
        <FocusController focusNodeId={focusNodeId} />
        <FitNodesController nodeIds={fitNodeIds} />
        <CenterNodeController centerNodeId={centerNodeId} requestNonce={centerNodeNonce} />
      </ReactFlow>
    </div>
  );
};
