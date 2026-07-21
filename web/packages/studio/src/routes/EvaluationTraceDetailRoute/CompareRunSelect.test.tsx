// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import { CompareRunSelect } from '@studio/routes/EvaluationTraceDetailRoute/CompareRunSelect';
import { render, screen } from '@studio/tests/util/render';

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
});
