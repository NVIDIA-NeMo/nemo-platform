// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { HighlightedText } from '@studio/components/AnonymizerRecordView/HighlightedText';
import { ReplacementMapTable } from '@studio/components/AnonymizerRecordView/ReplacementMapTable';
import type { AnonymizerRecord } from '@studio/components/AnonymizerRecordView/types';
import type { FC } from 'react';

interface AnonymizerRecordViewProps {
  readonly record: AnonymizerRecord;
  /** "Replaced" for the replace strategies, "Rewritten" for rewrite. */
  readonly outputHeading: string;
}

export const AnonymizerRecordView: FC<AnonymizerRecordViewProps> = ({ record, outputHeading }) => (
  <Stack gap="density-2xl">
    <Flex align="start" gap="density-2xl">
      <Stack className="flex-1 min-w-0" gap="density-md">
        <Text color="secondary" kind="label/regular/md">
          Original
        </Text>
        <HighlightedText
          emptyMessage="This record has no text."
          segments={record.originalSegments}
        />
      </Stack>
      <Stack className="flex-1 min-w-0" gap="density-md">
        <Text color="secondary" kind="label/regular/md">
          {outputHeading}
        </Text>
        <HighlightedText
          emptyMessage="No output was produced for this record."
          segments={record.replacedSegments}
        />
      </Stack>
    </Flex>

    <Stack gap="density-md">
      <Text color="secondary" kind="label/regular/md">
        Replacement Map
      </Text>
      {record.replacements.length ? (
        <ReplacementMapTable replacements={record.replacements} />
      ) : (
        <Text color="secondary" kind="body/regular/md">
          No entities were replaced in this record.
        </Text>
      )}
    </Stack>
  </Stack>
);
