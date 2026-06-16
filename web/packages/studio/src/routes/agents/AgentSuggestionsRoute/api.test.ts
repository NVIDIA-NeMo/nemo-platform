// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { applySuggestion } from '@studio/routes/agents/AgentSuggestionsRoute/api';
import type { OptimizationSuggestion } from '@studio/routes/agents/AgentSuggestionsRoute/types';

// `applySuggestion` calls `customFetch` only after validation passes; the
// mock lets us assert which steps actually hit the network and stub responses.
const customFetchMock = vi.fn();
vi.mock('@nemo/sdk/generated/fetchers/platform', () => ({
  customFetch: (...args: unknown[]) => customFetchMock(...args),
}));

// The api module imports SDK functions at top-level even though applySuggestion
// doesn't use them — stub them so the module loads cleanly.
vi.mock('@nemo/sdk/generated/platform/api', () => ({
  filesCreateFileset: vi.fn(),
  filesDownloadFile: vi.fn(),
  filesListFilesetFiles: vi.fn(),
  filesUploadFile: vi.fn(),
  modelsListModels: vi.fn(),
}));

vi.mock('@studio/constants/environment', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@studio/constants/environment')>();
  return { ...actual, PLATFORM_BASE_URL: 'https://platform.test' };
});

const WORKSPACE = 'ws-a';

const makeSuggestion = (
  overrides: Partial<OptimizationSuggestion> = {}
): OptimizationSuggestion => ({
  type: 'model_optimization',
  title: 't',
  detail: 'd',
  agent: 'support-bot',
  ...overrides,
});

const expectReject = async (
  suggestion: OptimizationSuggestion,
  workspace: string,
  matcher: RegExp
) => {
  await expect(applySuggestion(suggestion, workspace)).rejects.toThrow(matcher);
  expect(customFetchMock).not.toHaveBeenCalled();
};

beforeEach(() => {
  customFetchMock.mockReset();
});

describe('applySuggestion — path/method validation', () => {
  it('rejects non-allowlisted or unsafe paths before network access', async () => {
    const cases: Array<{
      apply: NonNullable<OptimizationSuggestion['apply']>;
      matcher: RegExp;
    }> = [
      {
        apply: {
          method: 'DELETE',
          path: '/apis/agents/v2/workspaces/ws-a/agents/support-bot',
        },
        matcher: /not an allowlisted optimizer action/,
      },
      {
        apply: {
          method: 'PATCH',
          path: '/apis/agents/v2/workspaces/ws-a/agents/support-bot',
          body: { llms: { llm: { model_name: 'mini-4b' } } },
        },
        matcher: /not an allowlisted optimizer action/,
      },
      {
        apply: { method: 'POST', path: '/x://evil/apis/agents/v2/workspaces/ws-a/agents' },
        matcher: /must not contain a scheme/,
      },
      {
        apply: { method: 'POST', path: '//evil/apis/agents/v2/workspaces/ws-a/agents' },
        matcher: /same-origin absolute path/,
      },
      {
        apply: { method: 'POST', path: '/apis/agents/v2/workspaces/ws-a/agents\x07' },
        matcher: /control characters/,
      },
      {
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/deployments?force=true',
          body: { agent: 'support-bot' },
        },
        matcher: /query string or fragment/,
      },
      {
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/deployments#frag',
          body: { agent: 'support-bot' },
        },
        matcher: /query string or fragment/,
      },
      {
        apply: { method: 'POST', path: '/apis/health' },
        matcher: /not a workspace-scoped Platform API path/,
      },
      {
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/other-ws/agents',
          body: { name: 'spoof' },
        },
        matcher: /workspace mismatch/,
      },
    ];

    for (const { apply, matcher } of cases) {
      customFetchMock.mockClear();
      await expectReject(makeSuggestion({ apply }), WORKSPACE, matcher);
    }
  });
});

describe('applySuggestion — identity binding', () => {
  it('rejects POST /agents without body.name', async () => {
    await expectReject(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/agents',
          body: {},
        },
      }),
      WORKSPACE,
      /body\.name must be a non-empty string/
    );
  });

  it('rejects POST /deployments targeting an undeclared agent', async () => {
    await expectReject(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/deployments',
          body: { agent: 'some-other-agent' },
        },
      }),
      WORKSPACE,
      /not suggestion\.agent .* or a sibling/
    );
  });

  it('allows POST /deployments targeting suggestion.agent directly', async () => {
    customFetchMock.mockResolvedValueOnce({ name: 'deploy-1' });
    const result = await applySuggestion(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/deployments',
          body: { agent: 'support-bot' },
        },
      }),
      WORKSPACE
    );
    expect(result).toEqual({ deploymentNames: ['deploy-1'], evalJobNames: [] });
    expect(customFetchMock).toHaveBeenCalledTimes(1);
  });

  it('allows POST /agents → POST /deployments for the declared sibling', async () => {
    customFetchMock
      .mockResolvedValueOnce({ name: 'support-bot-mini-4b' }) // POST /agents
      .mockResolvedValueOnce({ name: 'deploy-2' }); // POST /deployments

    const result = await applySuggestion(
      makeSuggestion({
        apply: [
          {
            method: 'POST',
            path: '/apis/agents/v2/workspaces/ws-a/agents',
            body: { name: 'support-bot-mini-4b' },
          },
          {
            method: 'POST',
            path: '/apis/agents/v2/workspaces/ws-a/deployments',
            body: { agent: 'support-bot-mini-4b' },
          },
        ],
      }),
      WORKSPACE
    );
    expect(result).toEqual({ deploymentNames: ['deploy-2'], evalJobNames: [] });
    expect(customFetchMock).toHaveBeenCalledTimes(2);
  });

  it('rejects POST /deployments for a sibling declared in a DIFFERENT apply', async () => {
    // The declaredAgentNames set is per-apply; names from a previous
    // applySuggestion call must not carry over.
    customFetchMock.mockResolvedValueOnce({ name: 'sibling-1' });
    await applySuggestion(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/agents',
          body: { name: 'sibling-1' },
        },
      }),
      WORKSPACE
    );
    customFetchMock.mockReset();

    await expectReject(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/deployments',
          body: { agent: 'sibling-1' },
        },
      }),
      WORKSPACE,
      /not suggestion\.agent .* or a sibling/
    );
  });
});

describe('applySuggestion — empty input', () => {
  it('rejects missing or empty apply steps', async () => {
    const cases: OptimizationSuggestion['apply'][] = [undefined, []];

    for (const apply of cases) {
      customFetchMock.mockClear();
      await expect(applySuggestion(makeSuggestion({ apply }), WORKSPACE)).rejects.toThrow(
        /no steps/
      );
      expect(customFetchMock).not.toHaveBeenCalled();
    }
  });
});

describe('applySuggestion — POST /jobs/evaluate identity binding', () => {
  it('allows submitting an evaluate-agent job for suggestion.agent', async () => {
    customFetchMock.mockResolvedValueOnce({ name: 'eval-job-1' });
    await applySuggestion(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
          body: { spec: { agent: 'support-bot', eval_config: 'eval.yaml' } },
        },
      }),
      WORKSPACE
    );
    expect(customFetchMock).toHaveBeenCalledTimes(1);
  });

  it('allows submitting an evaluate-agent job for a sibling declared earlier', async () => {
    customFetchMock
      .mockResolvedValueOnce({ name: 'support-bot-mini-4b' })
      .mockResolvedValueOnce({ name: 'deploy-1' })
      .mockResolvedValueOnce({ name: 'eval-job-2' });
    const result = await applySuggestion(
      makeSuggestion({
        apply: [
          {
            method: 'POST',
            path: '/apis/agents/v2/workspaces/ws-a/agents',
            body: { name: 'support-bot-mini-4b' },
          },
          {
            method: 'POST',
            path: '/apis/agents/v2/workspaces/ws-a/deployments',
            body: { agent: 'support-bot-mini-4b' },
          },
          {
            method: 'POST',
            path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
            body: {
              spec: { agent: 'support-bot-mini-4b', eval_config: 'eval.yaml' },
            },
          },
        ],
      }),
      WORKSPACE
    );
    expect(customFetchMock).toHaveBeenCalledTimes(3);
    // ApplyResult separates the deployment names (drives waitForDeployments)
    // from the eval-job names (drives waitForEvalJob + score lookup).
    expect(result).toEqual({
      deploymentNames: ['deploy-1'],
      evalJobNames: ['eval-job-2'],
    });
  });

  it('accepts a workspace-prefixed agent ref matching the apply workspace', async () => {
    customFetchMock.mockResolvedValueOnce({ name: 'eval-job-3' });
    await applySuggestion(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
          body: { spec: { agent: 'ws-a/support-bot', eval_config: 'eval.yaml' } },
        },
      }),
      WORKSPACE
    );
    expect(customFetchMock).toHaveBeenCalledTimes(1);
  });

  it('rejects an endpoint URL in body.spec.agent', async () => {
    await expectReject(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
          body: { spec: { agent: 'http://attacker.test', eval_config: 'eval.yaml' } },
        },
      }),
      WORKSPACE,
      /must be a platform agent ref, not an endpoint URL/
    );
  });

  it('rejects a cross-workspace agent ref', async () => {
    await expectReject(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
          body: { spec: { agent: 'other-ws/support-bot', eval_config: 'eval.yaml' } },
        },
      }),
      WORKSPACE,
      /workspace .* must match apply workspace/
    );
  });

  it('rejects an evaluate-agent job for an undeclared agent', async () => {
    await expectReject(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
          body: { spec: { agent: 'some-other-agent', eval_config: 'eval.yaml' } },
        },
      }),
      WORKSPACE,
      /not suggestion\.agent .* or a sibling/
    );
  });
});

describe('applySuggestion — cancel signal', () => {
  it('passes the abort signal through to customFetch', async () => {
    const controller = new AbortController();
    customFetchMock.mockResolvedValueOnce({ name: 'deploy-1' });
    await applySuggestion(
      makeSuggestion({
        apply: {
          method: 'POST',
          path: '/apis/agents/v2/workspaces/ws-a/deployments',
          body: { agent: 'support-bot' },
        },
      }),
      WORKSPACE,
      controller.signal
    );
    expect(customFetchMock).toHaveBeenCalledWith(
      expect.objectContaining({ signal: controller.signal })
    );
  });
});
