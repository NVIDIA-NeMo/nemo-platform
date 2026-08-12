// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ANNOTATION_COLOR,
  ANNOTATION_TEXT_COLOR,
} from '@nemo/common/src/components/ComparisonLineChart/consts';
import type { FC } from 'react';

interface Props {
  label: string;
  description?: string;
  color?: string;
  pointsUp: boolean;
  /** Which side of the arrow the text sits on, so callouts near the right edge stay in frame. */
  labelSide: 'left' | 'right';
  /** Injected by recharts when this is passed as a `<ReferenceLine label>`. */
  viewBox?: { x?: number; y?: number; width?: number; height?: number };
}

const ARROW_HALF_WIDTH = 5;
const ARROW_LENGTH = 9;
const TEXT_OFFSET = 12;

/**
 * Draws the arrowhead and callout text for a `ComparisonAnnotation`. The dashed shaft is the
 * `ReferenceLine` itself; this only renders what recharts has no primitive for.
 */
export const ComparisonAnnotationLabel: FC<Props> = ({
  label,
  description,
  color = ANNOTATION_COLOR,
  pointsUp,
  labelSide,
  viewBox,
}) => {
  const { x = 0, y = 0, height = 0 } = viewBox ?? {};
  const tipY = pointsUp ? y : y + height;
  const baseY = pointsUp ? tipY + ARROW_LENGTH : tipY - ARROW_LENGTH;
  const onLeft = labelSide === 'left';
  const textX = onLeft ? x - TEXT_OFFSET : x + TEXT_OFFSET;
  const textAnchor = onLeft ? 'end' : 'start';
  const textY = y + height / 2;

  return (
    <g>
      <polygon
        points={`${x},${tipY} ${x - ARROW_HALF_WIDTH},${baseY} ${x + ARROW_HALF_WIDTH},${baseY}`}
        fill={color}
      />
      <text
        x={textX}
        y={textY}
        textAnchor={textAnchor}
        fill={ANNOTATION_TEXT_COLOR}
        fontSize={20}
        fontWeight={700}
      >
        {label}
      </text>
      {description && (
        <text
          x={textX}
          y={textY + 16}
          textAnchor={textAnchor}
          fill={ANNOTATION_TEXT_COLOR}
          fontSize={11}
        >
          {description}
        </text>
      )}
    </g>
  );
};
