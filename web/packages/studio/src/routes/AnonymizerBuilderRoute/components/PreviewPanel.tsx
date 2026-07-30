// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Accordion,
  Banner,
  Button,
  CodeSnippet,
  Flex,
  Panel,
  Skeleton,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { AnonymizerRecordView } from '@studio/components/AnonymizerRecordView/AnonymizerRecordView';
import { buildAnonymizerRecord, outputColumn } from '@studio/components/AnonymizerRecordView/parse';
import type { UseAnonymizerPreview } from '@studio/routes/AnonymizerBuilderRoute/useAnonymizerPreview';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useMemo, useState, type FC, type ReactNode } from 'react';

const SKELETON_LINES = 8;
const REWRITTEN_SUFFIX = '_rewritten';

const SkeletonBlock: FC = () => (
  <Stack gap="density-sm">
    {Array.from({ length: SKELETON_LINES }, (_, index) => (
      <Skeleton key={index} />
    ))}
  </Stack>
);

const LoadingState: FC = () => (
  <Stack gap="density-2xl">
    <Flex align="start" gap="density-2xl">
      <Stack className="flex-1 min-w-0" gap="density-md">
        <Text color="secondary" kind="label/regular/md">
          Original
        </Text>
        <SkeletonBlock />
      </Stack>
      <Stack className="flex-1 min-w-0" gap="density-md">
        <Text color="secondary" kind="label/regular/md">
          Replaced
        </Text>
        <SkeletonBlock />
      </Stack>
    </Flex>
    <Stack gap="density-md">
      <Text color="secondary" kind="label/regular/md">
        Replacement Map
      </Text>
      <SkeletonBlock />
    </Stack>
  </Stack>
);

interface PreviewPanelProps {
  readonly preview: UseAnonymizerPreview;
  /** Rendered at the trailing end of the panel header — the Full Run submit button. */
  readonly slotActions: ReactNode;
}

export const PreviewPanel: FC<PreviewPanelProps> = ({ preview, slotActions }) => {
  const { result, logs, isPreviewing, error, hasRun } = preview;
  const { records, textColumn, failedRecords } = result;
  const [recordIndex, setRecordIndex] = useState(0);
  const [pagedRecords, setPagedRecords] = useState(records);

  // Reset the pager during render rather than in an effect, so a new result set never
  // paints the old record index first.
  if (pagedRecords !== records) {
    setPagedRecords(records);
    setRecordIndex(0);
  }

  const activeRow = records[recordIndex];
  const record = useMemo(
    () => (activeRow ? buildAnonymizerRecord(activeRow, textColumn) : undefined),
    [activeRow, textColumn]
  );
  const outputHeading =
    activeRow && outputColumn(activeRow, textColumn)?.endsWith(REWRITTEN_SUFFIX)
      ? 'Rewritten'
      : 'Replaced';

  return (
    <Panel
      className="flex-1 h-full min-w-0"
      density="standard"
      elevation="high"
      attributes={{ PanelContent: { className: 'flex-1 min-h-0 overflow-auto' } }}
      slotHeading={
        <Flex align="center" className="w-full" gap="density-md" justify="between">
          <Text kind="label/bold/xl">Preview</Text>
          {records.length > 0 ? (
            <Flex align="center" gap="density-sm">
              <Button
                aria-label="Previous record"
                disabled={recordIndex === 0}
                kind="tertiary"
                onClick={() => setRecordIndex((index) => index - 1)}
                type="button"
              >
                <ChevronLeft size={16} />
              </Button>
              <Text kind="body/regular/md">
                Record {recordIndex + 1} of {records.length}
              </Text>
              <Button
                aria-label="Next record"
                disabled={recordIndex >= records.length - 1}
                kind="tertiary"
                onClick={() => setRecordIndex((index) => index + 1)}
                type="button"
              >
                <ChevronRight size={16} />
              </Button>
            </Flex>
          ) : null}
          {slotActions}
        </Flex>
      }
      slotFooter={
        logs.length > 0 ? (
          <Accordion
            className="w-full"
            items={[
              {
                value: 'logs',
                slotTrigger: 'Logs',
                slotContent: (
                  <CodeSnippet
                    attributes={{ CodeSnippetCode: { className: 'max-h-[240px]' } }}
                    kind="block"
                    value={logs.join('\n')}
                  />
                ),
              },
            ]}
          />
        ) : null
      }
    >
      <Stack className="h-full" gap="density-lg">
        {error ? (
          <Banner kind="inline" status="error">
            {error}
          </Banner>
        ) : null}
        {failedRecords.length > 0 ? (
          <Banner kind="inline" status="warning">
            {failedRecords.length} record(s) failed during the preview run.
          </Banner>
        ) : null}
        {record ? (
          <AnonymizerRecordView outputHeading={outputHeading} record={record} />
        ) : isPreviewing ? (
          <LoadingState />
        ) : error ? null : (
          <Flex align="center" className="flex-1" justify="center">
            <Text color="secondary" kind="body/regular/md">
              {hasRun
                ? 'The preview run returned no records.'
                : 'Your records preview will appear here'}
            </Text>
          </Flex>
        )}
      </Stack>
    </Panel>
  );
};
