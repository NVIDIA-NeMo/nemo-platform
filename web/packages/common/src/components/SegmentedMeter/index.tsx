// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import { useState, type FC } from 'react';

export interface SegmentedMeterSegment {
  /** Proportional weight; segments are sized relative to the sum of all values. */
  value: number;
  /** CSS color for the segment fill (hex or var(--token)) — caller decides semantics. */
  color: string;
  /** Optional caption rendered below the bar, under this segment. */
  caption?: string;
}

interface Props {
  segments: SegmentedMeterSegment[];
  className?: string;
}

const MUTED_CLASS_NAME = 'text-placeholder';

export const SegmentedMeter: FC<Props> = ({ segments, className }) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const total = segments.reduce((sum, segment) => sum + Math.max(segment.value, 0), 0);

  if (total <= 0) {
    return null;
  }

  const captioned = segments.filter((segment) => segment.caption);
  const defaultCaptions =
    captioned.length <= 2 ? captioned : [captioned[0], captioned[captioned.length - 1]];
  const hoveredCaption = hoveredIndex !== null ? segments[hoveredIndex]?.caption : undefined;

  return (
    <div className={className}>
      <div className="flex h-3 gap-[2px]">
        {segments.map((segment, index) => (
          <div
            key={`${segment.color}-${index}`}
            data-testid="segmented-meter-segment"
            className="rounded"
            onMouseEnter={() => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex((current) => (current === index ? null : current))}
            // eslint-disable-next-line no-restricted-syntax
            style={{
              flexGrow: Math.max(segment.value, 0),
              flexBasis: 0,
              backgroundColor: segment.color,
            }}
          />
        ))}
      </div>
      {captioned.length > 0 ? (
        <div
          data-testid="segmented-meter-captions"
          className={hoveredCaption ? 'flex justify-start mt-1' : 'flex justify-between mt-1'}
        >
          {hoveredCaption ? (
            <Text kind="body/regular/sm" className={MUTED_CLASS_NAME}>
              {hoveredCaption}
            </Text>
          ) : (
            defaultCaptions.map((segment) => (
              <Text key={segment.caption} kind="body/regular/sm" className={MUTED_CLASS_NAME}>
                {segment.caption}
              </Text>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
};
