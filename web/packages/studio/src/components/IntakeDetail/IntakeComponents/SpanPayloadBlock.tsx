// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MarkdownContent } from '@nemo/common/src/components/MarkdownContent';
import { CodeSnippet, Flex, Spinner, Text } from '@nvidia/foundations-react-core';
import { IntakeErrorBanner } from '@studio/components/IntakeDetail/IntakeComponents/IntakeErrorBanner';
import { SpanPayloadChat } from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadChat';
import { SpanPayloadViewMode } from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadRendererControl';
import { type FC, useEffect, useMemo, useState } from 'react';

const LARGE_PAYLOAD_RENDER_DEFER_CHAR_LIMIT = 20_000;
const MAX_JSON_INDENTATION_DEPTH = 100;

/**
 * Shared renderer for span request/response payloads (the Input/Output sections
 * and any kind-specific payload, e.g. a retriever query). A scrollable code
 * block without copy/collapse controls, or a dashed empty state. Keeping this in
 * one place ensures every payload renders identically.
 */
interface SpanPayloadBlockProps {
  value: string | null | undefined;
  emptyMessage: string;
  viewMode?: SpanPayloadViewMode;
}

type JsonRenderResult = { ok: true; value: string } | { ok: false; message: string };

const isJsonWhitespace = (character: string): boolean =>
  character === ' ' || character === '\n' || character === '\r' || character === '\t';

const adjacentSignificantCharacter = (
  payload: string,
  startIndex: number,
  direction: 1 | -1
): string | null => {
  for (let index = startIndex; index >= 0 && index < payload.length; index += direction) {
    const character = payload[index];
    if (character !== undefined && !isJsonWhitespace(character)) return character;
  }
  return null;
};

const jsonIndent = (depth: number): string =>
  '  '.repeat(Math.min(depth, MAX_JSON_INDENTATION_DEPTH));

/** Pretty-print JSON punctuation without reparsing numeric values or reordering object keys. */
const formatJsonLosslessly = (payload: string): string => {
  // Validate first, but format the original lexical tokens. Round-tripping the
  // parsed value through JSON.stringify would round integers above MAX_SAFE_INTEGER.
  JSON.parse(payload);

  let formatted = '';
  let indentation = 0;
  let isInsideString = false;
  let isEscaped = false;

  for (let index = 0; index < payload.length; index += 1) {
    const character = payload[index];
    if (character === undefined) continue;

    if (isInsideString) {
      formatted += character;
      if (isEscaped) {
        isEscaped = false;
      } else if (character === '\\') {
        isEscaped = true;
      } else if (character === '"') {
        isInsideString = false;
      }
      continue;
    }

    if (isJsonWhitespace(character)) continue;

    if (character === '"') {
      isInsideString = true;
      formatted += character;
      continue;
    }

    if (character === '{' || character === '[') {
      formatted += character;
      indentation += 1;
      const matchingClose = character === '{' ? '}' : ']';
      if (adjacentSignificantCharacter(payload, index + 1, 1) !== matchingClose) {
        formatted += `\n${jsonIndent(indentation)}`;
      }
      continue;
    }

    if (character === '}' || character === ']') {
      indentation = Math.max(0, indentation - 1);
      const matchingOpen = character === '}' ? '{' : '[';
      if (adjacentSignificantCharacter(payload, index - 1, -1) !== matchingOpen) {
        formatted += `\n${jsonIndent(indentation)}`;
      }
      formatted += character;
      continue;
    }

    if (character === ',') {
      formatted += `,\n${jsonIndent(indentation)}`;
      continue;
    }

    formatted += character === ':' ? ': ' : character;
  }

  return formatted;
};

const JsonPayload: FC<{ payload: string; disableHighlighting: boolean }> = ({
  payload,
  disableHighlighting,
}) => {
  const result = useMemo<JsonRenderResult>(() => {
    try {
      return { ok: true, value: formatJsonLosslessly(payload) };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown JSON parse error';
      return { ok: false, message };
    }
  }, [payload]);

  if (!result.ok) {
    return (
      <IntakeErrorBanner
        heading="Cannot render as JSON"
        message={`The payload is not valid JSON. ${result.message}`}
      />
    );
  }

  return (
    <PayloadCodeBlock payload={result.value} language={disableHighlighting ? 'text' : 'json'} />
  );
};

const PayloadCodeBlock: FC<{ payload: string; language: 'json' | 'text' }> = ({
  payload,
  language,
}) => (
  <CodeSnippet
    value={payload}
    language={language}
    kind="block"
    attributes={{
      CodeSnippetActions: { className: 'hidden' },
      CodeSnippetCode: {
        className:
          'max-h-[420px] [&_code]:whitespace-pre-wrap [&_code]:break-words [&_pre]:whitespace-pre-wrap',
      },
    }}
  />
);

export const SpanPayloadBlock: FC<SpanPayloadBlockProps> = ({
  value,
  emptyMessage,
  viewMode = SpanPayloadViewMode.raw,
}) => {
  // Trim only to decide emptiness; render the original payload unchanged.
  const payload = value && value.trim() ? value : null;
  // Very large payloads can make the code renderer hold the main thread long
  // enough that the section looks blank. For those payloads, paint a spinner
  // first, then mount the renderer on the next macrotask.
  const shouldDeferRender =
    payload !== null && payload.length >= LARGE_PAYLOAD_RENDER_DEFER_CHAR_LIMIT;
  const [deferredRender, setDeferredRender] = useState<{
    payload: string;
    viewMode: SpanPayloadViewMode;
  } | null>(null);
  const showPayload =
    !shouldDeferRender ||
    (deferredRender?.payload === payload && deferredRender.viewMode === viewMode);

  useEffect(() => {
    if (!payload || !shouldDeferRender) return;

    // `setTimeout(..., 0)` gives React one committed paint with the spinner
    // before the large CodeSnippet mounts. This is render backpressure, not a
    // network loading state.
    const timeout = setTimeout(() => setDeferredRender({ payload, viewMode }), 0);
    return () => clearTimeout(timeout);
  }, [payload, shouldDeferRender, viewMode]);

  if (payload) {
    if (!showPayload) {
      return (
        <Flex
          align="center"
          justify="center"
          className="min-h-[160px] rounded-md border border-base bg-surface-raised p-density-xl"
        >
          <Spinner size="medium" aria-label="Rendering payload" />
        </Flex>
      );
    }

    switch (viewMode) {
      case SpanPayloadViewMode.raw:
        return <PayloadCodeBlock payload={payload} language="text" />;
      case SpanPayloadViewMode.markdown:
        return (
          <div className="max-h-[420px] min-w-0 overflow-auto rounded-md border border-base bg-surface-base p-density-lg">
            <MarkdownContent content={payload} />
          </div>
        );
      case SpanPayloadViewMode.json:
        return <JsonPayload payload={payload} disableHighlighting={shouldDeferRender} />;
      case SpanPayloadViewMode.chat:
        return <SpanPayloadChat payload={payload} />;
    }
  }

  return (
    <div className="flex min-h-[120px] items-center rounded-md border border-dashed border-base bg-surface-raised p-density-xl">
      <Text kind="body/regular/sm" className="text-secondary">
        {emptyMessage}
      </Text>
    </div>
  );
};
