// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeSnippet, Flex, Spinner, Text } from '@nvidia/foundations-react-core';
import { type FC, useEffect, useState } from 'react';

const LARGE_PAYLOAD_RENDER_DEFER_CHAR_LIMIT = 20_000;

/**
 * Shared renderer for span request/response payloads (the Input/Output sections
 * and any kind-specific payload, e.g. a retriever query). A scrollable code
 * block without copy/collapse controls, or a dashed empty state. Keeping this in
 * one place ensures every payload renders identically.
 */
export const SpanPayloadBlock: FC<{ value: string | null | undefined; emptyMessage: string }> = ({
  value,
  emptyMessage,
}) => {
  // Trim only to decide emptiness; render the original payload unchanged.
  const payload = value && value.trim() ? value : null;
  // Very large payloads can make the code renderer hold the main thread long
  // enough that the section looks blank. For those payloads, paint a spinner
  // first, then mount the renderer on the next macrotask.
  const shouldDeferRender =
    payload !== null && payload.length >= LARGE_PAYLOAD_RENDER_DEFER_CHAR_LIMIT;
  const [showPayload, setShowPayload] = useState(!shouldDeferRender);

  useEffect(() => {
    if (!shouldDeferRender) {
      setShowPayload(true);
      return;
    }

    setShowPayload(false);
    // `setTimeout(..., 0)` gives React one committed paint with the spinner
    // before the large CodeSnippet mounts. This is render backpressure, not a
    // network loading state.
    const timeout = setTimeout(() => setShowPayload(true), 0);
    return () => clearTimeout(timeout);
  }, [payload, shouldDeferRender]);

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

    return (
      <CodeSnippet
        value={payload}
        // Large payloads are already hard to inspect; skip async markdown/Shiki
        // highlighting so rendering is predictable and the full text appears.
        language={shouldDeferRender ? 'text' : 'markdown'}
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
  }

  return (
    <div className="flex min-h-[120px] items-center rounded-md border border-dashed border-base bg-surface-raised p-density-xl">
      <Text kind="body/regular/sm" className="text-secondary">
        {emptyMessage}
      </Text>
    </div>
  );
};
