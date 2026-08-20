// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TICK_STYLE } from '@nemo/common/src/components/charts/frame';
import { REFERENCE_LINE_COLOR } from '@nemo/common/src/components/charts/tokens';
import type { ChartReferenceLine } from '@nemo/common/src/components/charts/types';
import type { ReactElement } from 'react';
import { ReferenceLine } from 'recharts';

/**
 * Must stay a plain function: recharts dispatches chart children by element type, so wrapping this
 * in a component would hide the `<ReferenceLine>` and it would silently never render.
 */
export const renderReferenceLines = (lines: ChartReferenceLine[] = []): ReactElement[] =>
  lines.map((line, index) => (
    <ReferenceLine
      // Index included because `ChartReferenceLine` carries no id and two lines may share a y/label.
      key={`ref-${index}-${line.y}-${line.label ?? ''}`}
      y={line.y}
      stroke={line.color ?? REFERENCE_LINE_COLOR}
      strokeDasharray="4 4"
      label={
        line.label
          ? { value: line.label, position: 'insideTopRight', style: TICK_STYLE }
          : undefined
      }
    />
  ));
