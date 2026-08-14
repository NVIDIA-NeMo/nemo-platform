// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EntityEmptyState } from '@nemo/common/src/components/EntityEmptyState';
import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import type { Meta, StoryObj } from '@storybook/react';

const meta: Meta<typeof EntityEmptyState> = {
  title: 'Common/EntityEmptyState',
  component: EntityEmptyState,
  decorators: [
    (Story) => (
      <ToastProvider>
        <div className="h-[480px] w-[720px]">
          <Story />
        </div>
      </ToastProvider>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof EntityEmptyState>;

export const FirstUse: Story = {
  args: { entity: 'guardrails', variant: 'first-use', onCreate: () => {} },
};

export const NoResults: Story = {
  args: { entity: 'guardrails', variant: 'no-results', onClearFilters: () => {} },
};
