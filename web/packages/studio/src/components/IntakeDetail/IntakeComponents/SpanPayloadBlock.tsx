// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeSnippet, Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

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
  if (value && value.trim()) {
    return (
      <CodeSnippet
        value={value}
        language="markdown"
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
