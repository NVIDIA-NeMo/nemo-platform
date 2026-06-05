// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BASE_URL } from '@studio/constants/environment';
import {
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
});
