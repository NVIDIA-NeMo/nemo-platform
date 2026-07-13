// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DagCanvas } from '@studio/components/DagCanvas';
import {
  CardNode,
  type CardNodeData,
  type CardNodeType,
} from '@studio/components/DagCanvas/CardNode';
import { NODE_HEIGHT, NODE_WIDTH, layoutGraph } from '@studio/components/DagCanvas/layout';
import type { DagNode } from '@studio/components/DagCanvas/types';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type Edge, type Node, type NodeProps, Position } from '@xyflow/react';

// React Flow reads from an internal store/context that only exists inside a fully
// measured <ReactFlow> (needs ResizeObserver + real layout, absent in jsdom). Stub
// Handle for isolated CardNode tests, and stub ReactFlow to render each node's
// activation handler so DagCanvas's own onActivate → onNodeClick wiring is testable.
vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>();
  return {
    ...actual,
    Handle: () => null,
    Background: () => null,
    Controls: () => null,
    ReactFlow: ({ nodes }: { nodes: CardNodeType[] }) => (
      <div>
        {nodes.map((node) => (
          <button key={node.id} type="button" onClick={() => node.data.onActivate?.()}>
            {node.data.title}
          </button>
        ))}
      </div>
    ),
  };
});

const makeNode = (id: string): Node<CardNodeData> => ({
  id,
  position: { x: 0, y: 0 },
  data: { title: id },
});

describe('layoutGraph', () => {
  it('assigns a distinct position to every node', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')];
    const edges: Edge[] = [
      { id: 'a-b', source: 'a', target: 'b' },
      { id: 'b-c', source: 'b', target: 'c' },
    ];

    const result = layoutGraph(nodes, edges, 'TB');

    expect(result).toHaveLength(3);
    const ys = result.map((node) => node.position.y);
    // Top-to-bottom: each rank sits below the previous one.
    expect(new Set(ys).size).toBe(3);
    expect(result.every((node) => Number.isFinite(node.position.x))).toBe(true);
  });

  it('orients handles top/bottom for TB and left/right for LR', () => {
    const nodes = [makeNode('a'), makeNode('b')];
    const edges: Edge[] = [{ id: 'a-b', source: 'a', target: 'b' }];

    const [tb] = layoutGraph(nodes, edges, 'TB');
    expect(tb.targetPosition).toBe(Position.Top);
    expect(tb.sourcePosition).toBe(Position.Bottom);

    const [lr] = layoutGraph(nodes, edges, 'LR');
    expect(lr.targetPosition).toBe(Position.Left);
    expect(lr.sourcePosition).toBe(Position.Right);
  });

  it('moves a node off a skip edge that would otherwise run through it', () => {
    // a → b → c chained, plus a → c skipping over b. dagre stacks a and c in the
    // same column, so the straight a→c edge (and its label) would cross b.
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')];
    const edges: Edge[] = [
      { id: 'a-b', source: 'a', target: 'b' },
      { id: 'b-c', source: 'b', target: 'c' },
      { id: 'a-c', source: 'a', target: 'c', label: 'skip' },
    ];

    const result = layoutGraph(nodes, edges, 'TB');
    const byId = Object.fromEntries(result.map((n) => [n.id, n]));

    // The skip edge is drawn straight down a and c's shared column.
    const column = byId.a.position.x;
    expect(byId.c.position.x).toBeCloseTo(column);

    // b's card must not straddle that column.
    const bLeft = byId.b.position.x;
    const bRight = byId.b.position.x + NODE_WIDTH;
    expect(column < bLeft || column > bRight).toBe(true);
  });

  it('offsets positions from dagre centers by half the card size', () => {
    const [only] = layoutGraph([makeNode('solo')], [], 'TB');
    // A single node centers at (NODE_WIDTH/2, NODE_HEIGHT/2), so the top-left origin is (0, 0).
    expect(only.position.x).toBeCloseTo(0);
    expect(only.position.y).toBeCloseTo(0);
    expect(NODE_WIDTH).toBeGreaterThan(0);
    expect(NODE_HEIGHT).toBeGreaterThan(0);
  });
});

const renderCard = (data: CardNodeType['data']) =>
  render(<CardNode {...({ data } as unknown as NodeProps<CardNodeType>)} />);

describe('CardNode', () => {
  it('renders the title, type label, description, and tags', () => {
    renderCard({
      title: 'Instruction',
      type: 'LLM TEXT',
      description: 'Writes a question about the topic',
      tags: ['{{topic}}', '{{difficulty}}'],
    });
    expect(screen.getByText('Instruction')).toBeInTheDocument();
    expect(screen.getByText('LLM TEXT')).toBeInTheDocument();
    expect(screen.getByText('Writes a question about the topic')).toBeInTheDocument();
    expect(screen.getByText('{{topic}}')).toBeInTheDocument();
    expect(screen.getByText('{{difficulty}}')).toBeInTheDocument();
  });

  it('fires onActivate when clicked', async () => {
    const user = userEvent.setup();
    const onActivate = vi.fn();
    renderCard({ title: 'Deploy', onActivate });

    await user.click(screen.getByRole('button', { name: /Deploy/ }));

    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('is keyboard-activatable', async () => {
    const user = userEvent.setup();
    const onActivate = vi.fn();
    renderCard({ title: 'Evaluate', onActivate });

    await user.tab();
    await user.keyboard('{Enter}');

    expect(onActivate).toHaveBeenCalled();
  });
});

describe('DagCanvas', () => {
  it('bridges a node activation to onNodeClick with the node id and data', async () => {
    const user = userEvent.setup();
    const onNodeClick = vi.fn();
    const nodes: DagNode[] = [
      { id: 'train', data: { title: 'Train', type: 'CUSTOMIZER' } },
      { id: 'evaluate', data: { title: 'Evaluate' } },
    ];

    render(
      <DagCanvas
        nodes={nodes}
        edges={[{ source: 'train', target: 'evaluate' }]}
        onNodeClick={onNodeClick}
      />
    );

    await user.click(screen.getByRole('button', { name: 'Train' }));

    expect(onNodeClick).toHaveBeenCalledTimes(1);
    expect(onNodeClick).toHaveBeenCalledWith('train', nodes[0].data);
  });

  it('always calls the latest onNodeClick after the callback identity changes', async () => {
    const user = userEvent.setup();
    const first = vi.fn();
    const second = vi.fn();
    const nodes: DagNode[] = [{ id: 'train', data: { title: 'Train' } }];

    const { rerender } = render(<DagCanvas nodes={nodes} edges={[]} onNodeClick={first} />);
    // Swap in a fresh callback reference, mirroring a parent passing an inline arrow.
    rerender(<DagCanvas nodes={nodes} edges={[]} onNodeClick={second} />);

    await user.click(screen.getByRole('button', { name: 'Train' }));

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith('train', nodes[0].data);
  });
});
