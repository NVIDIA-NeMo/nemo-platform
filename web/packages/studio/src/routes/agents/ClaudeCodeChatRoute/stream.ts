// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { websiteLogger } from '@studio/util/logger';

interface ServerSentEvent {
  event?: string;
  data: string;
}

interface ParsedSseChunk {
  events: ServerSentEvent[];
  rest: string;
}

interface ClaudeCodeTextPart {
  type?: unknown;
  text?: unknown;
  name?: unknown;
}

interface ClaudeCodeMessage {
  content?: unknown;
}

interface ClaudeCodeStreamEvent {
  type?: unknown;
  message?: ClaudeCodeMessage;
}

export const parseSseChunk = (chunk: string): ParsedSseChunk => {
  const normalized = chunk.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const rest = blocks.pop() ?? '';

  return {
    rest,
    events: blocks
      .map((block) => {
        const lines = block.split('\n');
        let event: string | undefined;
        const dataLines: string[] = [];

        for (const line of lines) {
          if (line.startsWith('event:')) {
            event = line.slice('event:'.length).trim();
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice('data:'.length).replace(/^ /, ''));
          }
        }

        return { event, data: dataLines.join('\n') };
      })
      .filter((event) => event.event || event.data),
  };
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const getContentParts = (event: ClaudeCodeStreamEvent): ClaudeCodeTextPart[] => {
  const content = event.message?.content;
  if (!Array.isArray(content)) return [];
  return content.filter(isRecord);
};

export const getAssistantTextFromClaudeEvent = (event: unknown): string => {
  if (!isRecord(event) || event.type !== 'assistant') return '';

  const parts = getContentParts(event);
  const text = parts
    .map((part) => {
      if (part.type === 'text' && typeof part.text === 'string') return part.text;
      if (part.type === 'tool_use') {
        const toolName = typeof part.name === 'string' ? part.name : 'tool';
        return `\n\nUsing ${toolName}...`;
      }
      return '';
    })
    .filter(Boolean)
    .join('');

  return text;
};

export const parseJsonObject = (value: string): unknown => {
  if (!value) return undefined;
  try {
    return JSON.parse(value) as unknown;
  } catch (error) {
    websiteLogger.error(
      `Failed to parse Claude Code stream JSON: ${error instanceof Error ? error.message : String(error)}`
    );
    return undefined;
  }
};
