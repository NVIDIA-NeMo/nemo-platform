// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TraceSpanTree } from '@studio/components/IntakeDetail/TraceDetailSpanTree';
import { mockSpanById, mockTraceById } from '@studio/mocks/intake/telemetry';
import { render, screen } from '@studio/tests/util/render';
import { buildSpanTree, type SessionTrajectory } from '@studio/util/intakeTelemetry';
import userEvent from '@testing-library/user-event';

const LONG_TRACE_NAME =
  'Answer a customer policy question with enough detail that the trajectory label is truncated';

const makeTrajectory = (): SessionTrajectory => {
  const trace = { ...mockTraceById('trace-agent-run-001')!, name: LONG_TRACE_NAME };
  const spans = [mockSpanById('span-root-001')!, mockSpanById('span-llm-001')!];
  return { trace, spans, spanTree: buildSpanTree(spans) };
};

describe('TraceSpanTree', () => {
  it('collapses trace and span branches while preserving branch selection', async () => {
    const user = userEvent.setup();
    const onSelectTrace = vi.fn();
    const onSelectSpan = vi.fn();
    render(
      <TraceSpanTree
        trajectories={[makeTrajectory()]}
        activeTraceId="trace-agent-run-001"
        activeSpanId={null}
        onSelectTrace={onSelectTrace}
        onSelectSpan={onSelectSpan}
      />
    );

    const traceTrigger = screen.getByTitle('View trace');
    expect(traceTrigger).toHaveAttribute('data-state', 'open');
    await user.click(traceTrigger);
    expect(traceTrigger).toHaveAttribute('data-state', 'closed');
    expect(onSelectTrace).toHaveBeenCalledWith('trace-agent-run-001');

    await user.click(traceTrigger);
    const rootSpanLabel = screen.getByText('Answer customer policy question', {
      selector: 'span.truncate',
    });
    const rootSpanTrigger = rootSpanLabel.closest('summary')!;
    expect(rootSpanTrigger).toHaveAttribute('data-state', 'open');
    await user.click(rootSpanTrigger);
    expect(rootSpanTrigger).toHaveAttribute('data-state', 'closed');
    expect(onSelectSpan).toHaveBeenCalledWith('span-root-001', 'trace-agent-run-001');
  });

  it('shows the full trajectory label in a tooltip on hover', async () => {
    const user = userEvent.setup();
    render(
      <TraceSpanTree
        trajectories={[makeTrajectory()]}
        activeSpanId={null}
        onSelectSpan={vi.fn()}
      />
    );

    const traceLabel = screen.getByText(LONG_TRACE_NAME, { selector: 'span.truncate' });
    const tooltip = screen.getByRole('tooltip', { name: LONG_TRACE_NAME });
    expect(tooltip).toHaveAttribute('data-state', 'closed');

    await user.hover(traceLabel);
    expect(tooltip).toHaveAttribute('data-state', 'open');
  });
});
