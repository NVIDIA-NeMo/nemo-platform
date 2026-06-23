// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { CodeSnippet, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { IntakeAnnotationsPanel } from '@studio/components/IntakeAnnotationsPanel';
import { KeyValueColumns } from '@nemo/studio-plugins-example/intake-trace-detail/KeyValueColumns';
import {
  buildSpanLlmEntries,
  buildSpanSummaryEntries,
} from '@nemo/studio-plugins-example/intake-trace-detail/spanKeyValues';
import { Activity, ArrowDownToLine, ArrowUpFromLine, Coins, StickyNote } from 'lucide-react';
import { type FC, useMemo } from 'react';

const SPAN_INPUT_SECTION = 'span-input';
const SPAN_OUTPUT_SECTION = 'span-output';
const SPAN_SUMMARY_SECTION = 'span-summary';
const SPAN_LLM_SECTION = 'span-llm';
const SPAN_ANNOTATIONS_SECTION = 'span-annotations';

const DEFAULT_OPEN_SECTIONS = [SPAN_LLM_SECTION, SPAN_INPUT_SECTION, SPAN_OUTPUT_SECTION];

interface SpanPayloadContentProps {
  value: string | null | undefined;
  emptyMessage: string;
}

const SpanPayloadContent: FC<SpanPayloadContentProps> = ({ value, emptyMessage }) => {
  const content = value?.trim();

  if (content) {
    return (
      <CodeSnippet
        value={content}
        language="markdown"
        kind="block"
        collapsible
        defaultOpen
        attributes={{
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

interface SpanMetadataAccordionsProps {
  span: Span;
  workspace: string;
}

export const SpanMetadataAccordions: FC<SpanMetadataAccordionsProps> = ({ span, workspace }) => {
  const summaryEntries = useMemo(
    () => buildSpanSummaryEntries(span, { workspace }),
    [span, workspace]
  );
  const llmEntries = useMemo(() => buildSpanLlmEntries(span), [span]);

  return (
    <IntakeAccordion
      variant="section"
      defaultValue={DEFAULT_OPEN_SECTIONS}
      items={[
        {
          value: SPAN_LLM_SECTION,
          slotLabel: (
            <Flex align="center" gap="density-sm" className="min-w-0">
              <Coins className="shrink-0" aria-hidden />
              <Text kind="body/semibold/sm">LLM, tokens, &amp; cost</Text>
            </Flex>
          ),
          slotContent: (
            <Stack className="min-w-0">
              <KeyValueColumns entries={llmEntries} />
            </Stack>
          ),
        },
        {
          value: SPAN_INPUT_SECTION,
          slotLabel: (
            <Flex align="center" gap="density-sm" className="min-w-0">
              <ArrowDownToLine className="shrink-0" aria-hidden />
              <Text kind="body/semibold/sm">Input</Text>
            </Flex>
          ),
          slotContent: (
            <Stack className="min-w-0">
              <SpanPayloadContent
                value={span.input}
                emptyMessage="No input payload was captured for this span."
              />
            </Stack>
          ),
        },
        {
          value: SPAN_OUTPUT_SECTION,
          slotLabel: (
            <Flex align="center" gap="density-sm" className="min-w-0">
              <ArrowUpFromLine className="shrink-0" aria-hidden />
              <Text kind="body/semibold/sm">Output</Text>
            </Flex>
          ),
          slotContent: (
            <Stack className="min-w-0">
              <SpanPayloadContent
                value={span.output}
                emptyMessage="No output payload was captured for this span."
              />
            </Stack>
          ),
        },
        {
          value: SPAN_SUMMARY_SECTION,
          slotLabel: (
            <Flex align="center" gap="density-sm" className="min-w-0">
              <Activity className="shrink-0" aria-hidden />
              <Text kind="body/semibold/sm">Metadata</Text>
            </Flex>
          ),
          slotContent: (
            <Stack className="min-w-0">
              <KeyValueColumns entries={summaryEntries} />
            </Stack>
          ),
        },
        {
          value: SPAN_ANNOTATIONS_SECTION,
          slotLabel: (
            <Flex align="center" gap="density-sm" className="min-w-0">
              <StickyNote className="shrink-0" aria-hidden />
              <Text kind="body/semibold/sm">Annotations</Text>
            </Flex>
          ),
          slotContent: (
            <Stack className="min-w-0">
              <IntakeAnnotationsPanel
                workspace={workspace}
                spanId={span.span_id}
                sessionId={span.session_id}
              />
            </Stack>
          ),
        },
      ]}
    />
  );
};
