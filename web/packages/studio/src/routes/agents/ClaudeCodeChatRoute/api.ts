// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { parseJsonObject, parseSseChunk } from '@studio/routes/agents/ClaudeCodeChatRoute/stream';
import type { ClaudeCodeStreamHandlers } from '@studio/routes/agents/ClaudeCodeChatRoute/types';

const CLAUDE_CODE_API_BASE_PATH = '/apis/studio/v2/coding-agents';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const claudeCodeApiUrl = (path: string): string =>
  `${PLATFORM_BASE_URL}${CLAUDE_CODE_API_BASE_PATH}${path}`;

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

const getStreamErrorMessage = (payload: unknown): string => {
  if (!isRecord(payload)) return 'Claude Code stream failed';
  if (typeof payload.stderr === 'string' && payload.stderr) return payload.stderr;
  if (typeof payload.detail === 'string' && payload.detail) return payload.detail;
  if (typeof payload.message === 'string' && payload.message) return payload.message;
  return 'Claude Code stream failed';
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

  handlers.onClaudeEvent(parseJsonObject(event.data));
  return true;
};

export const streamClaudeCodeMessage = async ({
  sessionId,
  message,
  signal,
  handlers,
}: {
  sessionId: string;
  message: string;
  signal: AbortSignal;
  handlers: ClaudeCodeStreamHandlers;
}): Promise<void> => {
  const response = await fetch(claudeCodeApiUrl(`/sessions/${sessionId}/messages`), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message }),
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
