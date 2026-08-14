// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SegmentedMeter } from '@nemo/common/src/components/SegmentedMeter';
import type { Meta, StoryObj } from '@storybook/react';

const meta: Meta<typeof SegmentedMeter> = {
  component: SegmentedMeter,
  title: 'Studio Common/SegmentedMeter',
  decorators: [
    (Story) => (
      <div className="w-[250px]">
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof SegmentedMeter>;

export const Default: Story = {
  args: {
    segments: [
      { value: 62, color: '#6b7280', caption: '62% zero' },
      { value: 34, color: '#4ade80', caption: '34% typical' },
      { value: 4, color: '#84cc16', caption: '4% max' },
    ],
  },
};

export const SingleSegment: Story = {
  args: {
    segments: [{ value: 100, color: '#3987e5', caption: '100% populated' }],
  },
};

export const ManySegments: Story = {
  args: {
    segments: [
      { value: 20, color: '#6b7280', caption: '20% zero' },
      { value: 20, color: '#84cc16', caption: '20% low' },
      { value: 20, color: '#22c55e', caption: '20% typical' },
      { value: 20, color: '#eab308', caption: '20% high' },
      { value: 20, color: '#ef4444', caption: '20% outliers' },
    ],
  },
};

export const NoCaptions: Story = {
  args: {
    segments: [
      { value: 62, color: '#6b7280' },
      { value: 34, color: '#4ade80' },
      { value: 4, color: '#84cc16' },
    ],
  },
};
