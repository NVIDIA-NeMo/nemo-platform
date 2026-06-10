// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BASE_URL, PLATFORM_BASE_URL } from '@studio/constants/environment';
import { parseJsonObject, parseSseChunk } from '@studio/routes/agents/ClaudeCodeChatRoute/stream';
import type {
  ClaudeCodeAssistantHistoryPart,
  ClaudeCodeHistorySession,
  ClaudeCodePermissionDecision,
  ClaudeCodePermissionRequest,
  ClaudeCodeSessionHistory,
  ClaudeCodeSessionHistoryItem,
  ClaudeCodeStreamHandlers,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';

const CLAUDE_CODE_API_BASE_PATH = '/apis/studio/v2/coding-agents';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const claudeCodeApiUrl = (path: string): string =>
  `${PLATFORM_BASE_URL}${CLAUDE_CODE_API_BASE_PATH}${path}`;

const getStudioBaseUrl = (): string | undefined => {
  if (typeof window === 'undefined') return undefined;

  const normalizedBaseUrl = BASE_URL.replace(/\/+$/, '');
  const basePath = normalizedBaseUrl && normalizedBaseUrl !== '/' ? normalizedBaseUrl : '';
  return `${window.location.origin}${basePath}`;
};

const getStudioPathname = (): string | undefined => {
  if (typeof window === 'undefined') return undefined;
  return window.location.pathname;
};

export const CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY = [
  'claude-code',
  'history',
  'sessions',
] as const;

export const getClaudeCodeSessionHistoryQueryKey = (sessionId: string) =>
  ['claude-code', 'history', 'session', sessionId] as const;

const getResponseErrorMessage = async (response: Response, fallback: string): Promise<string> => {
  const text = await response.text();
  if (!text) return fallback;

  try {
    const body = JSON.parse(text) as unknown;
    if (isRecord(body) && typeof body.detail === 'string') return body.detail;
  } catch {
    return text;
  }

  return text;
};

export const createClaudeCodeSession = async (): Promise<string> => {
  const response = await fetch(claudeCodeApiUrl('/sessions'), {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(
      await getResponseErrorMessage(response, 'Failed to create Claude Code session')
    );
  }

  const body = (await response.json()) as unknown;
  if (!isRecord(body) || typeof body.session_id !== 'string') {
    throw new Error('Claude Code session response did not include a session id');
  }

  return body.session_id;
};

const getString = (value: unknown): string => (typeof value === 'string' ? value : '');

const getNumber = (value: unknown): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : 0;

const getStringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const parseHistorySession = (value: unknown): ClaudeCodeHistorySession | undefined => {
  if (!isRecord(value)) return undefined;
  const sessionId = getString(value.session_id);
  if (!sessionId) return undefined;

  return {
    session_id: sessionId,
    mtime: getNumber(value.mtime),
    first_prompt: getString(value.first_prompt),
    message_count: getNumber(value.message_count),
    token_count: getNumber(value.token_count),
    tool_call_count: getNumber(value.tool_call_count),
    tool_calls: getStringArray(value.tool_calls),
  };
};

const parseAssistantPart = (value: unknown): ClaudeCodeAssistantHistoryPart | undefined => {
  if (!isRecord(value)) return undefined;

  if (value.type === 'text') {
    const text = getString(value.text);
    return text ? { type: 'text', text } : undefined;
  }

  if (value.type === 'tool_use') {
    return {
      type: 'tool_use',
      name: getString(value.name) || 'tool',
      input: isRecord(value.input) ? value.input : {},
    };
  }

  return undefined;
};

const parseSessionHistoryItem = (value: unknown): ClaudeCodeSessionHistoryItem | undefined => {
  if (!isRecord(value)) return undefined;

  if (value.kind === 'user') {
    const text = getString(value.text);
    return text ? { kind: 'user', text } : undefined;
  }

  if (value.kind === 'assistant' && Array.isArray(value.parts)) {
    const parts = value.parts
      .map(parseAssistantPart)
      .filter((part): part is ClaudeCodeAssistantHistoryPart => part !== undefined);
    return parts.length ? { kind: 'assistant', parts } : undefined;
  }

  return undefined;
};

export const listClaudeCodeHistorySessions = async (): Promise<ClaudeCodeHistorySession[]> => {
  const response = await fetch(claudeCodeApiUrl('/history/sessions'));

  if (!response.ok) {
    throw new Error(await getResponseErrorMessage(response, 'Failed to load Claude Code history'));
  }

  const body = (await response.json()) as unknown;
  if (!Array.isArray(body)) return [];

  return body
    .map(parseHistorySession)
    .filter((session): session is ClaudeCodeHistorySession => session !== undefined);
};

export const getClaudeCodeSessionHistory = async (
  sessionId: string
): Promise<ClaudeCodeSessionHistory> => {
  const response = await fetch(
    claudeCodeApiUrl(`/history/sessions/${encodeURIComponent(sessionId)}`)
  );

  if (!response.ok) {
    throw new Error(await getResponseErrorMessage(response, 'Failed to load Claude Code session'));
  }

  const body = (await response.json()) as unknown;
  if (!isRecord(body)) {
    throw new Error('Claude Code session history response was not an object');
  }

  return {
    session_id: getString(body.session_id) || sessionId,
    items: Array.isArray(body.items)
      ? body.items
          .map(parseSessionHistoryItem)
          .filter((item): item is ClaudeCodeSessionHistoryItem => item !== undefined)
      : [],
  };
};

const getStreamErrorMessage = (payload: unknown): string => {
  if (!isRecord(payload)) return 'Claude Code stream failed';
  if (typeof payload.stderr === 'string' && payload.stderr) return payload.stderr;
  if (typeof payload.detail === 'string' && payload.detail) return payload.detail;
  if (typeof payload.message === 'string' && payload.message) return payload.message;
  return 'Claude Code stream failed';
};

const parsePermissionRequest = (payload: unknown): ClaudeCodePermissionRequest | undefined => {
  if (!isRecord(payload) || typeof payload.request_id !== 'string') return undefined;
  if (typeof payload.tool_name !== 'string' || !payload.tool_name) return undefined;
  if (!isRecord(payload.input) || Array.isArray(payload.input)) return undefined;

  return {
    requestId: payload.request_id,
    toolName: payload.tool_name,
    input: payload.input,
    toolUseId: typeof payload.tool_use_id === 'string' ? payload.tool_use_id : undefined,
  };
};

const handleSseEvent = (
  event: { event?: string; data: string },
  handlers: ClaudeCodeStreamHandlers
): boolean => {
  if (event.event === 'done') {
    handlers.onDone();
    return true;
  }

  if (event.event === 'error') {
    handlers.onError(new Error(getStreamErrorMessage(parseJsonObject(event.data))));
    return false;
  }

  if (event.event === 'permission_request') {
    const request = parsePermissionRequest(parseJsonObject(event.data));
    if (!request) {
      handlers.onError(new Error('Claude Code permission request was malformed'));
      return false;
    }
    handlers.onPermissionRequest(request);
    return true;
  }

  handlers.onClaudeEvent(parseJsonObject(event.data));
  return true;
};

export const resolveClaudeCodePermission = async ({
  sessionId,
  requestId,
  decision,
}: {
  sessionId: string;
  requestId: string;
  decision: ClaudeCodePermissionDecision;
}): Promise<void> => {
  const response = await fetch(
    claudeCodeApiUrl(`/sessions/${sessionId}/permissions/${requestId}`),
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        approved: decision.approved,
        reason: decision.reason,
        updated_input: decision.updatedInput,
      }),
    }
  );

  if (!response.ok) {
    throw new Error(
      await getResponseErrorMessage(response, 'Failed to resolve Claude Code permission')
    );
  }
};

export const streamClaudeCodeMessage = async ({
  sessionId,
  message,
  studioBaseUrl,
  studioPathname,
  workspace,
  signal,
  handlers,
}: {
  sessionId: string;
  message: string;
  studioBaseUrl?: string;
  studioPathname?: string;
  workspace?: string;
  signal: AbortSignal;
  handlers: ClaudeCodeStreamHandlers;
}): Promise<void> => {
  const response = await fetch(claudeCodeApiUrl(`/sessions/${sessionId}/messages`), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      studio_base_url: studioBaseUrl ?? getStudioBaseUrl(),
      studio_pathname: studioPathname ?? getStudioPathname(),
      workspace,
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(await getResponseErrorMessage(response, 'Failed to send Claude Code message'));
  }
  if (!response.body) {
    throw new Error('Claude Code response did not include a stream');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = '';
  let shouldCancelReader = true;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        shouldCancelReader = false;
        break;
      }

      buffered += decoder.decode(value, { stream: true });
      const parsed = parseSseChunk(buffered);
      buffered = parsed.rest;

      for (const event of parsed.events) {
        if (!handleSseEvent(event, handlers)) return;
      }
    }

    buffered += decoder.decode();
    if (buffered) {
      const parsed = parseSseChunk(`${buffered}\n\n`);
      for (const event of parsed.events) {
        if (!handleSseEvent(event, handlers)) return;
      }
    }
  } finally {
    if (shouldCancelReader) {
      await reader.cancel().catch(() => undefined);
    }
    reader.releaseLock();
  }
};
