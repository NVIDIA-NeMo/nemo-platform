// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import { ComparisonTable } from '@studio/components/dataViews/ComparisonTable/ComparisonTable';
import {
  COMPARISON_EVALUATIONS,
  COMPARISON_EVALUATIONS_WIDE,
} from '@studio/components/dataViews/ComparisonTable/storyData';

const meta = {
  component: ComparisonTable,
  title: 'Components/Comparison table',
  decorators: [
    (Story) => (
      <div className="h-[520px] w-full max-w-6xl">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ComparisonTable>;

export default meta;
type Story = StoryObj<typeof meta>;

export const SharedEvalConfig: Story = {
  args: { evaluations: COMPARISON_EVALUATIONS },
};

/** Scroll horizontally: the metric and baseline columns stay pinned. */
export const ManyRuns: Story = {
  args: {
    evaluations: COMPARISON_EVALUATIONS_WIDE,
    lowerIsBetterMetrics: ['latency_s'],
  },
};

export const Empty: Story = {
  args: { evaluations: [] },
};
