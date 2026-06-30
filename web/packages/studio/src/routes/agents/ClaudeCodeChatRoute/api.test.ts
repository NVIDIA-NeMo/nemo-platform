// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BASE_URL } from '@studio/constants/environment';
import {
  getClaudeCodeSessionHistory,
  listClaudeCodeSkills,
  resolveClaudeCodeInput,
  resolveClaudeCodePermission,
  streamClaudeCodeMessage,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';

const getExpectedStudioBaseUrl = (): string => {
  const normalizedBaseUrl = BASE_URL.replace(/\/+$/, '');
  const basePath = normalizedBaseUrl && normalizedBaseUrl !== '/' ? normalizedBaseUrl : '';
  return `${window.location.origin}${basePath}`;
};

describe('Claude Code API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts messages with the active workspace', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('event: done\ndata: \n\n', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await streamClaudeCodeMessage({
      sessionId: 'session-1',
      message: 'list agents',
      workspace: 'default',
      signal: new AbortController().signal,
      handlers: {
        onClaudeEvent: vi.fn(),
        onInputRequest: vi.fn(),
        onPermissionRequest: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/session-1/messages'),
      expect.objectContaining({
        body: JSON.stringify({
          message: 'list agents',
          studio_base_url: getExpectedStudioBaseUrl(),
          studio_pathname: window.location.pathname,
          workspace: 'default',
        }),
        method: 'POST',
      })
    );
  });

  it('keeps historical chat artifact selections when loading a session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session_id: 'session-1',
          items: [],
          chat_artifacts: {
            selections: [
              { label: 'Agent', value: 'cat-identifier' },
              { label: 'Model', value: '`cloud, nvidia/example` - good for this agent' },
            ],
            files: [],
            links: [{ label: 'Agents', destination: 'agents', href: '/workspaces/default/agents' }],
            jobs: [
              {
                name: 'agent-eval-1',
                job_type: 'agent_evaluation',
                source: 'evaluator',
                href: '/workspaces/default/agents/evaluations/agent-eval-1',
              },
            ],
            tools: [],
          },
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const history = await getClaudeCodeSessionHistory('session-1');

    expect(history.chat_artifacts.selections).toEqual([
      { label: 'Agent', value: 'cat-identifier' },
      { label: 'Model', value: 'cloud, nvidia/example' },
    ]);
    expect(history.chat_artifacts.links).toEqual([
      { label: 'Agents', destination: 'agents', href: '/workspaces/default/agents' },
    ]);
    expect(history.chat_artifacts.jobs).toEqual([
      {
        name: 'agent-eval-1',
        job_type: 'agent_evaluation',
        source: 'evaluator',
        href: '/workspaces/default/agents/evaluations/agent-eval-1',
      },
    ]);
  });

  it('emits structured permission requests from SSE events', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          [
            'event: permission_request',
            'data: {"request_id":"request-1","tool_name":"Bash","input":{"command":"ls"},"tool_use_id":"tool-1"}',
            '',
            'event: done',
            'data: ',
            '',
          ].join('\n'),
          { status: 200 }
        )
      );
    vi.stubGlobal('fetch', fetchMock);

    const onPermissionRequest = vi.fn();

    await streamClaudeCodeMessage({
      sessionId: 'session-1',
      message: 'list files',
      signal: new AbortController().signal,
      handlers: {
        onClaudeEvent: vi.fn(),
        onInputRequest: vi.fn(),
        onPermissionRequest,
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    });

    expect(onPermissionRequest).toHaveBeenCalledWith({
      requestId: 'request-1',
      toolName: 'Bash',
      input: { command: 'ls' },
      toolUseId: 'tool-1',
    });
  });

  it('fails closed when permission requests omit required fields', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          [
            'event: permission_request',
            'data: {"request_id":"request-1","input":{"command":"ls"}}',
            '',
          ].join('\n'),
          { status: 200 }
        )
      );
    vi.stubGlobal('fetch', fetchMock);

    const onPermissionRequest = vi.fn();
    const onError = vi.fn();

    await streamClaudeCodeMessage({
      sessionId: 'session-1',
      message: 'list files',
      signal: new AbortController().signal,
      handlers: {
        onClaudeEvent: vi.fn(),
        onInputRequest: vi.fn(),
        onPermissionRequest,
        onDone: vi.fn(),
        onError,
      },
    });

    expect(onPermissionRequest).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Claude Code permission request was malformed' })
    );
  });

  it('fails closed when permission request input is an array', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          [
            'event: permission_request',
            'data: {"request_id":"request-1","tool_name":"Bash","input":[]}',
            '',
          ].join('\n'),
          { status: 200 }
        )
      );
    vi.stubGlobal('fetch', fetchMock);

    const onPermissionRequest = vi.fn();
    const onError = vi.fn();

    await streamClaudeCodeMessage({
      sessionId: 'session-1',
      message: 'list files',
      signal: new AbortController().signal,
      handlers: {
        onClaudeEvent: vi.fn(),
        onInputRequest: vi.fn(),
        onPermissionRequest,
        onDone: vi.fn(),
        onError,
      },
    });

    expect(onPermissionRequest).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Claude Code permission request was malformed' })
    );
  });

  it('posts approval decisions using the backend permission shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await resolveClaudeCodePermission({
      sessionId: 'session-1',
      requestId: 'request-1',
      decision: {
        approved: true,
        updatedInput: { command: 'ls' },
      },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/session-1/permissions/request-1'),
      expect.objectContaining({
        body: JSON.stringify({
          approved: true,
          updated_input: { command: 'ls' },
        }),
        method: 'POST',
      })
    );
  });

  it('loads Claude Code skill metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            name: 'inference',
            claude_name: 'nemo-inference',
            description: 'Use NeMo Platform inference.',
            source: 'nemo-platform',
            source_path: 'packages/nemo_platform_ext/src/nemo_platform_ext/skills/inference',
            install_path: '.claude/skills/nemo-inference/SKILL.md',
            installed: false,
          },
        ]),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(listClaudeCodeSkills()).resolves.toEqual([
      {
        name: 'inference',
        claude_name: 'nemo-inference',
        description: 'Use NeMo Platform inference.',
        source: 'nemo-platform',
        source_path: 'packages/nemo_platform_ext/src/nemo_platform_ext/skills/inference',
        install_path: '.claude/skills/nemo-inference/SKILL.md',
        installed: false,
      },
    ]);
  });

  it('emits structured blocking input requests from SSE events', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          [
            'event: input_request',
            'data: {"request_id":"request-1","kind":"agent","input":{"title":"Pick agent"}}',
            '',
          ].join('\n'),
          { status: 200 }
        )
      );
    vi.stubGlobal('fetch', fetchMock);

    const onInputRequest = vi.fn();

    await streamClaudeCodeMessage({
      sessionId: 'session-1',
      message: 'pick agent',
      signal: new AbortController().signal,
      handlers: {
        onClaudeEvent: vi.fn(),
        onInputRequest,
        onPermissionRequest: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    });

    expect(onInputRequest).toHaveBeenCalledWith({
      requestId: 'request-1',
      kind: 'agent',
      input: { title: 'Pick agent' },
    });
  });

  it('emits structured dataset file input requests from SSE events', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          [
            'event: input_request',
            'data: {"request_id":"request-1","kind":"dataset_file","input":{"title":"Pick dataset"}}',
            '',
          ].join('\n'),
          { status: 200 }
        )
      );
    vi.stubGlobal('fetch', fetchMock);

    const onInputRequest = vi.fn();

    await streamClaudeCodeMessage({
      sessionId: 'session-1',
      message: 'pick dataset',
      signal: new AbortController().signal,
      handlers: {
        onClaudeEvent: vi.fn(),
        onInputRequest,
        onPermissionRequest: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    });

    expect(onInputRequest).toHaveBeenCalledWith({
      requestId: 'request-1',
      kind: 'dataset_file',
      input: { title: 'Pick dataset' },
    });
  });

  it('emits structured model input requests from SSE events', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          [
            'event: input_request',
            'data: {"request_id":"request-1","kind":"model","input":{"title":"Pick model"}}',
            '',
          ].join('\n'),
          { status: 200 }
        )
      );
    vi.stubGlobal('fetch', fetchMock);

    const onInputRequest = vi.fn();

    await streamClaudeCodeMessage({
      sessionId: 'session-1',
      message: 'pick model',
      signal: new AbortController().signal,
      handlers: {
        onClaudeEvent: vi.fn(),
        onInputRequest,
        onPermissionRequest: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    });

    expect(onInputRequest).toHaveBeenCalledWith({
      requestId: 'request-1',
      kind: 'model',
      input: { title: 'Pick model' },
    });
  });

  it('posts blocking input decisions using the backend input shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await resolveClaudeCodeInput({
      sessionId: 'session-1',
      requestId: 'request-1',
      decision: {
        value: { agent: 'react-agent' },
      },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/session-1/inputs/request-1'),
      expect.objectContaining({
        body: JSON.stringify({
          skipped: undefined,
          value: { agent: 'react-agent' },
        }),
        method: 'POST',
      })
    );
  });

  it('preserves tool use ids from session history', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session_id: 'session-1',
          items: [
            {
              kind: 'assistant',
              parts: [
                {
                  type: 'tool_use',
                  id: 'toolu_job',
                  name: 'job_progress',
                  input: { job_name: 'studio-job-1' },
                },
              ],
            },
          ],
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getClaudeCodeSessionHistory('session-1')).resolves.toEqual({
      session_id: 'session-1',
      chat_artifacts: {
        agent: undefined,
        coding_agent_model: undefined,
        files: [],
        links: [],
        jobs: [{ name: 'studio-job-1' }],
        model: undefined,
        model_source: undefined,
        selections: [],
        tools: ['job_progress'],
        workspace: undefined,
      },
      items: [
        {
          kind: 'assistant',
          parts: [
            {
              type: 'tool_use',
              id: 'toolu_job',
              name: 'job_progress',
              input: { job_name: 'studio-job-1' },
            },
          ],
        },
      ],
    });
  });
});
