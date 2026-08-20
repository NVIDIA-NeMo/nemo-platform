// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import { CodeSnippet, Text } from '@nvidia/foundations-react-core';
import { IntakeErrorBanner } from '@studio/components/IntakeDetail/IntakeComponents/IntakeErrorBanner';
import { type FC, useMemo } from 'react';

const CHAT_ROLES: ReadonlySet<string> = new Set([
  'system',
  'developer',
  'user',
  'assistant',
  'tool',
  'function',
]);

interface TraceChatMessage {
  role: string;
  content: string;
  name?: string;
  details?: Record<string, unknown>;
}

type ChatPayloadParseResult =
  | { ok: true; messages: TraceChatMessage[] }
  | { ok: false; message: string };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const serializeValue = (value: unknown): string => {
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown serialization error';
    return `[Unable to serialize value: ${message}]`;
  }
};

const contentPartText = (part: unknown): string => {
  if (typeof part === 'string') return part;
  if (!isRecord(part)) return String(part ?? '');
  if (typeof part['text'] === 'string') return part['text'];
  if (typeof part['content'] === 'string') return part['content'];
  if (typeof part['refusal'] === 'string') return part['refusal'];

  const imageUrl = part['image_url'];
  if (typeof imageUrl === 'string') return `Image: ${imageUrl}`;
  if (isRecord(imageUrl) && typeof imageUrl['url'] === 'string') {
    return `Image: ${imageUrl['url']}`;
  }

  return serializeValue(part);
};

const messageContentText = (content: unknown): string => {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(contentPartText).filter(Boolean).join('\n\n');
  if (content === null || content === undefined) return '';
  return serializeValue(content);
};

const messageText = (message: Record<string, unknown>): string => {
  const content = messageContentText(message['content'] ?? message['parts']);
  const refusal = messageContentText(message['refusal']);
  return [content, refusal].filter(Boolean).join('\n\n');
};

const parseMessage = (value: unknown): TraceChatMessage | null => {
  if (!isRecord(value) || typeof value['role'] !== 'string') return null;
  const role = value['role'].toLowerCase();
  if (!CHAT_ROLES.has(role)) return null;

  const details: Record<string, unknown> = {};
  if (value['tool_calls'] !== undefined) details['tool_calls'] = value['tool_calls'];
  if (value['function_call'] !== undefined) details['function_call'] = value['function_call'];
  if (value['tool_call_id'] !== undefined) details['tool_call_id'] = value['tool_call_id'];

  return {
    role,
    content: messageText(value),
    name: typeof value['name'] === 'string' ? value['name'] : undefined,
    details: Object.keys(details).length > 0 ? details : undefined,
  };
};

const choiceMessageCandidates = (choices: unknown[]): unknown[] =>
  choices.flatMap((choice) => {
    if (!isRecord(choice)) return [];
    const message = choice['message'] ?? choice['delta'];
    if (!isRecord(message)) return [];
    return [typeof message['role'] === 'string' ? message : { ...message, role: 'assistant' }];
  });

const streamedChoiceMessages = (chunks: unknown[]): unknown[] => {
  const messages = new Map<
    string,
    {
      role: string;
      content: string;
      toolCalls: unknown[];
      functionCalls: unknown[];
    }
  >();

  for (const chunk of chunks) {
    if (!isRecord(chunk) || !Array.isArray(chunk['choices'])) continue;
    for (const [position, choice] of chunk['choices'].entries()) {
      if (!isRecord(choice)) continue;
      const delta = choice['delta'] ?? choice['message'];
      if (!isRecord(delta)) continue;

      const choiceIndex =
        typeof choice['index'] === 'number' || typeof choice['index'] === 'string'
          ? String(choice['index'])
          : String(position);
      const current = messages.get(choiceIndex) ?? {
        role: 'assistant',
        content: '',
        toolCalls: [],
        functionCalls: [],
      };
      if (typeof delta['role'] === 'string') current.role = delta['role'];
      current.content += messageText(delta);
      if (delta['tool_calls'] !== undefined) current.toolCalls.push(delta['tool_calls']);
      if (delta['function_call'] !== undefined) current.functionCalls.push(delta['function_call']);
      messages.set(choiceIndex, current);
    }
  }

  return Array.from(messages.values(), (message) => ({
    role: message.role,
    content: message.content,
    ...(message.toolCalls.length > 0 ? { tool_calls: message.toolCalls } : {}),
    ...(message.functionCalls.length > 0 ? { function_call: message.functionCalls } : {}),
  }));
};

const candidateMessages = (value: unknown): unknown[] | null => {
  if (Array.isArray(value)) {
    if (value.every((item) => isRecord(item) && typeof item['role'] === 'string')) return value;
    const streamedMessages = streamedChoiceMessages(value);
    return streamedMessages.length > 0 ? streamedMessages : value;
  }
  if (!isRecord(value)) return null;

  if (Array.isArray(value['messages'])) return value['messages'];

  if (Array.isArray(value['choices'])) {
    const messages = choiceMessageCandidates(value['choices']);
    if (messages.length > 0) return messages;
  }

  if (Array.isArray(value['output'])) {
    const messages = value['output'].filter(
      (item) => isRecord(item) && (item['type'] === 'message' || typeof item['role'] === 'string')
    );
    if (messages.length > 0) return messages;
  }

  if (typeof value['output_text'] === 'string') {
    return [{ role: 'assistant', content: value['output_text'] }];
  }

  if (Array.isArray(value['input'])) return value['input'];
  if (typeof value['input'] === 'string') return [{ role: 'user', content: value['input'] }];
  if (typeof value['role'] === 'string') return [value];

  return null;
};

const parseChatPayload = (payload: string): ChatPayloadParseResult => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown JSON parse error';
    return {
      ok: false,
      message: `Chat rendering requires a JSON payload. ${message}`,
    };
  }

  const candidates = candidateMessages(parsed);
  if (!candidates?.length) {
    return {
      ok: false,
      message:
        'No OpenAI-compatible messages were found. Expected a message array, a messages field, a choices response, or a Responses API output.',
    };
  }

  const messages: TraceChatMessage[] = [];
  for (const [index, candidate] of candidates.entries()) {
    const message = parseMessage(candidate);
    if (!message) {
      return {
        ok: false,
        message: `Message ${index + 1} does not have a supported OpenAI-compatible role and content shape.`,
      };
    }
    messages.push(message);
  }

  return { ok: true, messages };
};

const roleLabel = (message: TraceChatMessage): string => {
  const role = `${message.role.charAt(0).toUpperCase()}${message.role.slice(1)}`;
  return message.name ? `${role} · ${message.name}` : role;
};

const messageSurfaceClass = (role: string): string => {
  if (role === 'user') {
    return 'border-[var(--border-color-accent-teal)] bg-[var(--background-color-accent-teal-subtle)] rounded-br-sm';
  }
  if (role === 'assistant') {
    return 'border-base border-l-4 border-l-[var(--border-color-brand)] bg-surface-base rounded-bl-sm';
  }
  return 'border-base bg-surface-raised';
};

interface SpanPayloadChatProps {
  payload: string;
}

/** Read-only transcript renderer for OpenAI-compatible request and response payloads. */
export const SpanPayloadChat: FC<SpanPayloadChatProps> = ({ payload }) => {
  const result = useMemo(() => parseChatPayload(payload), [payload]);

  if (!result.ok) {
    return <IntakeErrorBanner heading="Cannot render as chat" message={result.message} />;
  }

  return (
    <ol
      aria-label="Chat transcript"
      className="m-0 flex max-h-[420px] min-w-0 list-none flex-col gap-density-md overflow-auto rounded-md border border-base bg-surface-sunken p-density-lg"
    >
      {result.messages.map((message, index) => {
        const isUser = message.role === 'user';
        return (
          <li
            key={`${message.role}-${message.name ?? 'anonymous'}-${index}`}
            data-message-role={message.role}
            className={`flex w-full flex-col gap-density-xs ${isUser ? 'items-end' : 'items-start'}`}
          >
            <Text kind="body/semibold/sm" className="text-secondary capitalize">
              {roleLabel(message)}
            </Text>
            <div
              className={`max-w-[min(88%,52rem)] rounded-lg border px-density-lg py-density-md shadow-sm ${messageSurfaceClass(message.role)}`}
            >
              {message.content ? (
                <MessageContent content={message.content} />
              ) : (
                <Text kind="body/regular/sm" className="text-secondary italic">
                  No text content
                </Text>
              )}
              {message.details ? (
                <CodeSnippet
                  value={serializeValue(message.details)}
                  language="json"
                  kind="block"
                  attributes={{
                    CodeSnippetActions: { className: 'hidden' },
                    CodeSnippetCode: {
                      className:
                        'mt-density-sm max-h-[220px] [&_code]:whitespace-pre-wrap [&_code]:break-words [&_pre]:whitespace-pre-wrap',
                    },
                  }}
                />
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
};
