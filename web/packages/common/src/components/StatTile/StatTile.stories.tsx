// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StatTile, type StatTileProps } from '@nemo/common/src/components/StatTile/index';
import { Grid } from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';

const meta: Meta<typeof StatTile> = {
  component: StatTile,
  title: 'Studio Common/StatTile',
};

export default meta;

type Story = StoryObj<typeof StatTile>;

export const Default: Story = {
  args: {
    label: 'Final Training Loss',
    value: '0.6420',
    hint: '-0.4600 from start',
    hintStatus: 'success',
  },
};

export const WithoutHint: Story = {
  args: {
    label: 'Steps Completed',
    value: '1,240 / 2,000',
  },
};

export const Unavailable: Story = {
  args: {
    label: 'Final Validation Loss',
    value: '—',
  },
};

export const WithTrailingLabel: Story = {
  args: {
    label: 'gen_kl_error',
    value: '5.4e-4',
    trailingLabel: 'ok',
    trailingLabelStatus: 'success',
    hint: 'flag above 1e-3',
  },
};

export const TrailingLabelWarning: Story = {
  args: {
    label: 'approx_entropy',
    value: '0.31',
    trailingLabel: 'falling',
    trailingLabelStatus: 'warning',
    hint: 'entropy collapse risk',
  },
};

export const DiagnosticsRow: Story = {
  render: () => (
    <Grid cols={{ base: 1, md: 2, lg: 4 }} gap="density-xl">
      <StatTile
        label="gen_kl_error"
        value="5.4e-4"
        trailingLabel="ok"
        trailingLabelStatus="success"
        hint="flag above 1e-3"
      />
      <StatTile
        label="token_mult_prob_error"
        value="0.4%"
        trailingLabel="ok"
        trailingLabelStatus="success"
        hint="flag above 1-2%"
      />
      <StatTile
        label="sampling_importance_ratio"
        value="1.002"
        trailingLabel="ok"
        trailingLabelStatus="success"
        hint="should hover near 1"
      />
      <StatTile
        label="approx_entropy"
        value="0.31"
        trailingLabel="falling"
        trailingLabelStatus="warning"
        hint="entropy collapse risk"
      />
    </Grid>
  ),
};

export const Borderless: Story = {
  render: () => (
    <Grid cols={2} gap="density-xl" className="max-w-sm">
      {SUMMARY_TILES.map((tile) => (
        <StatTile key={tile.label} {...tile} bordered={false} />
      ))}
    </Grid>
  ),
};

export const HintStatuses: Story = {
  render: () => (
    <Grid cols={{ base: 1, md: 2, lg: 4 }} gap="density-xl">
      <StatTile label="Success" value="0.6420" hint="-0.4600 from start" hintStatus="success" />
      <StatTile label="Warning" value="4.1%" hint="hit length limit" hintStatus="warning" />
      <StatTile label="Error" value="0.5800" hint="+0.1000 from start" hintStatus="error" />
      <StatTile label="Neutral" value="18" hint="no change" hintStatus="neutral" />
    </Grid>
  ),
};

const SUMMARY_TILES: StatTileProps[] = [
  {
    label: 'Final Training Loss',
    value: '0.6420',
    hint: '-0.4600 from start',
    hintStatus: 'success',
  },
  {
    label: 'Final Validation Loss',
    value: '0.5800',
    hint: '+0.1000 from start',
    hintStatus: 'error',
  },
  { label: 'Steps Completed', value: '1,240 / 2,000' },
  { label: 'Epochs Completed', value: '2 / 3' },
];

export const AsARow: Story = {
  render: () => (
    <Grid cols={{ base: 1, md: 2, lg: 4 }} gap="density-xl">
      {SUMMARY_TILES.map((tile) => (
        <StatTile key={tile.label} {...tile} />
      ))}
    </Grid>
  ),
};
