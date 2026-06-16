// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { jobsGetJob } from '@nemo/sdk/generated/platform/api';
import type { PlatformJobResponse } from '@nemo/sdk/generated/platform/schema';
import { ROUTES } from '@studio/constants/routes';
import { JOB_PROGRESS_JOB_TYPE } from '@studio/routes/agents/ClaudeCodeChatRoute/jobProgressConsts';
import { JobProgressToolCall } from '@studio/routes/agents/ClaudeCodeChatRoute/JobProgressToolCall';
import type { ClaudeCodeToolArgs } from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import { getClaudeCodeChatRoute } from '@studio/routes/utils';
import { renderRoute, screen } from '@studio/tests/util/render';

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>()),
  jobsGetJob: vi.fn(),
}));

const jobsGetJobMock = vi.mocked(jobsGetJob);
const workspace = 'default';

const createJob = (overrides: Partial<PlatformJobResponse> = {}): PlatformJobResponse =>
  ({
    attempt_id: 'attempt-1',
    description: 'Import data into the workspace',
    fileset: 'fileset-1',
    id: 'job-id-1',
    name: 'studio-job-1',
    platform_spec: {},
    source: 'platform',
    status: 'completed',
    workspace,
    ...overrides,
  }) as PlatformJobResponse;

const renderToolCall = (args: ClaudeCodeToolArgs) =>
  renderRoute(<JobProgressToolCall args={args} />, {
    history: getClaudeCodeChatRoute(workspace),
    routes: [
      {
        path: ROUTES.workspace.claudeCodeChat,
        element: <JobProgressToolCall args={args} />,
      },
    ],
  });

beforeEach(() => {
  jobsGetJobMock.mockReset().mockResolvedValue(createJob());
});

describe('JobProgressToolCall', () => {
  it('renders status for the job id supplied by the tool call', async () => {
    renderToolCall({ job_name: 'studio-job-1' });

    expect(await screen.findByText('studio-job-1')).toBeInTheDocument();
    expect(jobsGetJobMock).toHaveBeenCalledWith(workspace, 'studio-job-1', expect.any(AbortSignal));
    expect(await screen.findByText('Import data into the workspace')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'View details' })).toHaveAttribute(
      'href',
      '/workspaces/default/jobs/studio-job-1'
    );
  });

  it('links agent evaluation jobs to the agent evaluation details page when requested', async () => {
    jobsGetJobMock.mockResolvedValue(
      createJob({ description: 'Evaluate an agent', name: 'eval-job-1', source: 'evaluator' })
    );

    renderToolCall({
      job_name: 'eval-job-1',
      job_type: JOB_PROGRESS_JOB_TYPE.AGENT_EVALUATION,
    });

    expect(await screen.findByText('eval-job-1')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'View details' })).toHaveAttribute(
      'href',
      '/workspaces/default/agents/evaluations/eval-job-1'
    );
  });

  it('shows a recoverable missing-job state', async () => {
    jobsGetJobMock.mockRejectedValue({ response: { status: 404 } });

    renderToolCall({ job_name: 'missing-job' });

    expect(await screen.findByText('Job "missing-job" could not be found.')).toBeInTheDocument();
  });
});
