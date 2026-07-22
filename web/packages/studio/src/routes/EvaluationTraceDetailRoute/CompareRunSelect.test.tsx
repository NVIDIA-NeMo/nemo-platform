// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import { CompareRunSelect } from '@studio/routes/EvaluationTraceDetailRoute/CompareRunSelect';
import { render, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const run = (
  evaluationName: string,
  sessionId: string,
  traceId: string
): EvaluationSessionResponse =>
  ({
    workspace: 'default',
    evaluation_name: evaluationName,
    session_id: sessionId,
    trace_id: traceId,
    root_span_id: `span-${traceId}`,
    started_at: '2026-01-01T00:00:00Z',
    status: 'success',
  }) as EvaluationSessionResponse;

describe('CompareRunSelect', () => {
  const onChange = vi.fn();
  // Radix Select needs these pointer/layout APIs that jsdom does not implement.
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('shows a disabled loading placeholder while runs load', () => {
    render(
      <CompareRunSelect
        runs={[]}
        currentTraceId="trace-0"
        value={null}
        onChange={onChange}
        isLoading
      />
    );
    expect(screen.getByText('Loading other runs')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('is disabled with an empty placeholder when there are no other runs', () => {
    // The only run is the primary trace, which is never an option.
    render(
      <CompareRunSelect
        runs={[run('eval-a', 'sess-0', 'trace-0')]}
        currentTraceId="trace-0"
        value={null}
        onChange={onChange}
      />
    );
    expect(screen.getByText('No runs to compare to')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('is enabled with the fixed compare label once other runs exist', () => {
    render(
      <CompareRunSelect
        runs={[run('eval-a', 'sess-0', 'trace-0'), run('eval-b', 'sess-1', 'trace-1')]}
        currentTraceId="trace-0"
        value={null}
        onChange={onChange}
      />
    );
    expect(screen.getByText('Compare against evaluation run')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toBeEnabled();
  });
  it('collapses single-trial evaluations and nests multi-trial ones', async () => {
    const user = userEvent.setup();
    render(
      <CompareRunSelect
        runs={[
          run('primary-eval', 'sess-prim', 'trace-0'), // current — excluded
          run('solo-eval', 'sess-SOLO1', 'trace-solo'), // 1 trial → collapsed
          run('multi-eval', 'sess-MULTA', 'trace-m1'), // 2 trials → nested
          run('multi-eval', 'sess-MULTB', 'trace-m2'),
        ]}
        currentTraceId="trace-0"
        value={null}
        onChange={onChange}
      />
    );

    await user.click(screen.getByRole('combobox'));

    // Single-trial eval collapses to one option; no standalone heading for it.
    expect(screen.getByRole('option', { name: 'solo-eval · Trial SOLO1' })).toBeInTheDocument();
    expect(screen.queryByText('solo-eval', { exact: true })).not.toBeInTheDocument();

    // Multi-trial eval keeps a heading with its trials nested beneath.
    expect(screen.getByText('multi-eval')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'multi-eval · Trial MULTA' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'multi-eval · Trial MULTB' })).toBeInTheDocument();
  });
});
