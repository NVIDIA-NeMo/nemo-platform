// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Tag, Text } from '@nvidia/foundations-react-core';
import type { TextSegment } from '@studio/components/AnonymizerRecordView/types';
import { entityTagColor } from '@studio/routes/AnonymizerBuilderRoute/constants';
import type { FC } from 'react';

interface HighlightedTextProps {
  readonly segments: readonly TextSegment[];
  readonly emptyMessage: string;
}

export const HighlightedText: FC<HighlightedTextProps> = ({ segments, emptyMessage }) =>
  segments.length ? (
    <Text className="whitespace-pre-wrap break-words" kind="body/regular/md">
      {segments.map((segment, index) => {
        if (!segment.label) return <span key={index}>{segment.text}</span>;
        const color = entityTagColor(segment.label);
        return (
          <span className="inline-flex items-center gap-density-2xs" key={index}>
            <Tag color={color} readOnly>
              {segment.text}
            </Tag>
            <Tag color={color} kind="outline" readOnly>
              {segment.label}
            </Tag>
          </span>
        );
      })}
    </Text>
  ) : (
    <Text color="secondary" kind="body/regular/md">
      {emptyMessage}
    </Text>
  );
