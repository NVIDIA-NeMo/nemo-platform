// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EvalJobLogsPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/EvalJobLogsPanel';
import { render, screen } from '@studio/tests/util/render';

const useJobLogsMock = vi.fn();
vi.mock('@nemo/common/src/hooks/useJobLogs', () => ({
  useJobLogs: (...args: unknown[]) => useJobLogsMock(...args),
}));

beforeEach(() => {
  useJobLogsMock.mockReset();
});

describe('EvalJobLogsPanel', () => {
  it('requests logs for the job and shows the total in the heading', async () => {
    useJobLogsMock.mockReturnValue({
      data: [
        { timestamp: '2026-07-07T09:26:07.691656', message: '[stderr] starting run' },
        {
          timestamp: '2026-07-07T09:26:08.100000',
          message: '[stderr] Traceback (most recent call last):',
        },
      ],
      isLoading: false,
      error: null,
      total: 2,
      refetch: vi.fn(),
    });

    render(
      <EvalJobLogsPanel
        workspace="demo-epa"
        jobName="nemo-agents-plugin-ujbp4jo7"
        jobStatus="error"
      />
    );

    // The hook is called with the eval job name (which is also the platform job name).
    expect(useJobLogsMock).toHaveBeenCalledWith(
      expect.objectContaining({ workspace: 'demo-epa', name: 'nemo-agents-plugin-ujbp4jo7' })
    );
    expect(await screen.findByText('Logs (2)')).toBeInTheDocument();
  });

  it('shows an empty message when there are no logs', async () => {
    useJobLogsMock.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      total: 0,
      refetch: vi.fn(),
    });

    render(<EvalJobLogsPanel workspace="demo-epa" jobName="eval-empty" jobStatus="completed" />);

    expect(
      await screen.findByText('No logs recorded for this evaluation job.')
    ).toBeInTheDocument();
  });
});
