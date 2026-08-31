// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack } from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';
import { GrpoRewardPanel } from '@studio/components/CustomizationOverview/GrpoRewardPanel';
import { GrpoTrainingHealthPanel } from '@studio/components/CustomizationOverview/GrpoTrainingHealthPanel';
import { RunConfigurationPanel } from '@studio/components/CustomizationOverview/RunConfigurationPanel';
import {
  grpoCustomizationJob,
  grpoStatusDetails,
} from '@studio/mocks/customizer/customization-jobs';
import type { CustomizationStatusDetailsWithMetrics } from '@studio/types/customization';
import { getGrpoProgressTiles, getGrpoSummaryTiles } from '@studio/util/customizations';
import { buildRewardChartData } from '@studio/util/grpoMetrics';

const meta: Meta<typeof GrpoRewardPanel> = {
  component: GrpoRewardPanel,
  title: 'Customization/GRPO Overview',
};

export default meta;

type Story = StoryObj<typeof GrpoRewardPanel>;

const telemetry = {
  step: 500,
  maxSteps: 500,
  epoch: 1,
  numEpochs: 1,
  checkpointPath: 'default/grpo-output-fileset/checkpoints/step-500',
};

const overview = (details: CustomizationStatusDetailsWithMetrics) => (
  <Stack gap="density-xl">
    <GrpoRewardPanel
      reward={buildRewardChartData(details)}
      metrics={getGrpoSummaryTiles(details, true)}
      progress={getGrpoProgressTiles(telemetry, { isTerminal: true, duration: '2h 15m' })}
    />
    <GrpoTrainingHealthPanel statusDetails={details} />
    <RunConfigurationPanel
      customization={grpoCustomizationJob}
      telemetry={telemetry}
      onViewConfiguration={() => {}}
    />
  </Stack>
);

/** A completed run: the mean and the validation overlay. */
export const Completed: Story = {
  render: () => overview(grpoStatusDetails as CustomizationStatusDetailsWithMetrics),
};

/** Reward reported, diagnostics not — the health panel drops out rather than opening onto nothing. */
export const RewardOnly: Story = {
  render: () =>
    overview({
      metrics: { train_reward: grpoStatusDetails.metrics.train_reward },
    } as CustomizationStatusDetailsWithMetrics),
};

/** A run that has reported nothing yet. */
export const NoData: Story = {
  render: () => overview({} as CustomizationStatusDetailsWithMetrics),
};
