// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import { AddColumnPalette } from '@studio/components/AddColumnPalette';

const meta = {
  component: AddColumnPalette,
  title: 'Components/AddColumnPalette',
  parameters: {
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => (
      <div className="h-dvh w-[264px] border-r border-base bg-surface-base p-4">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AddColumnPalette>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The full palette: Sampler broken out into sub-types, then the other column families. */
export const Default: Story = {};
