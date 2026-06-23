// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeSnippet, Stack, Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

interface SpanCallResultPanelProps {
  input?: string | null;
  output?: string | null;
}

interface PayloadBlockProps {
  label: 'Call' | 'Result';
  value?: string | null;
  accentClassName: string;
}

const PayloadBlock: FC<PayloadBlockProps> = ({ label, value, accentClassName }) => {
  const content = value?.trim();

  return (
    <Stack gap="density-sm" className="min-w-0">
      <Text kind="label/regular/sm" className="text-secondary">
        {label}
      </Text>
      <div
        className={`min-w-0 rounded-md border border-base bg-surface-raised pl-3 ${accentClassName}`}
      >
        {content ? (
          <CodeSnippet
            value={content}
            language="python"
            kind="block"
            collapsible={false}
            defaultOpen
            attributes={{
              CodeSnippetCode: {
                className:
                  'max-h-[420px] [&_code]:whitespace-pre-wrap [&_code]:break-words [&_pre]:whitespace-pre-wrap',
              },
            }}
          />
        ) : (
          <Text kind="body/regular/sm" className="px-density-md py-density-lg text-secondary">
            —
          </Text>
        )}
      </div>
    </Stack>
  );
};

/** Agent00 span body: Call (input) and Result (output) only. */
export const SpanCallResultPanel: FC<SpanCallResultPanelProps> = ({ input, output }) => (
  <Stack gap="density-xl" className="min-w-0">
    <PayloadBlock label="Call" value={input} accentClassName="border-l-4 border-l-sky-500" />
    <PayloadBlock label="Result" value={output} accentClassName="border-l-4 border-l-amber-500" />
  </Stack>
);
