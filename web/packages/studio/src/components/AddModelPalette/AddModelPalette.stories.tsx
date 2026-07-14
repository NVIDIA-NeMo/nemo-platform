// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import { AddModelPalette } from '@studio/components/AddModelPalette';
import type { BuilderModel } from '@studio/routes/DataDesignerJobBuildRoute/models';

const meta = {
  component: AddModelPalette,
  title: 'Components/AddModelPalette',
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    modelGroups: [],
    onAddModel: () => {},
    onSelectModel: () => {},
  },
  decorators: [
    (Story) => (
      <div className="h-dvh w-[264px] border-r border-base bg-surface-base p-4">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AddModelPalette>;

export default meta;
type Story = StoryObj<typeof meta>;

const NEMOTRON_MODEL = 'nvidia/llama-3.3-nemotron-super-49b-v1';

const models: BuilderModel[] = [
  {
    id: 'model-0',
    alias: 'default',
    model: NEMOTRON_MODEL,
    provider: 'nvidia',
    inferenceParams: { temperature: 0.7 },
  },
  {
    id: 'model-1',
    alias: 'judge',
    model: 'nvidia/llama-3.1-nemotron-70b-instruct',
    provider: 'nvidia',
    inferenceParams: { temperature: 0, max_tokens: 1024 },
  },
];

/** A few configured models, the second selected for editing. */
export const WithModels: Story = {
  args: { models, selectedId: 'model-1' },
};

export const Empty: Story = {
  args: { models: [], selectedId: null },
};
