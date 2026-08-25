// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import type { RlGRPOTraining, RlJobOutput } from '@nemo/sdk/generated/customizer/schema';
import { Button, Flex, Grid, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import type { CustomizationTrainingTelemetry } from '@studio/types/customization';
import { isGrpoJob, type CustomizationJob } from '@studio/util/customizationBackend';
import { getBaseModel, getGrpoRunConfig } from '@studio/util/customizations';
import { Cog } from 'lucide-react';
import type { FC } from 'react';

interface Props {
  customization: CustomizationJob;
  telemetry: CustomizationTrainingTelemetry;
  onViewConfiguration: () => void;
}

export const RunConfigurationPanel: FC<Props> = ({
  customization,
  telemetry,
  onViewConfiguration,
}) => (
  <Panel
    elevation="high"
    slotHeading={
      <Flex className="w-full" justify="between">
        <Stack gap="density-xs">
          <Text kind="label/bold/lg">Run configuration</Text>
          <Text kind="body/regular/sm" className="text-secondary">
            How this customization job was set up and where its output landed.
          </Text>
        </Stack>
        <Button
          kind="tertiary"
          size="small"
          onClick={onViewConfiguration}
          className="-ml-density-md self-start"
        >
          <Cog />
          View Job Configuration
        </Button>
      </Flex>
    }
  >
    <Stack gap="density-xl">
      <Grid cols={{ base: 1, md: 2, lg: 3 }} gap="density-xl">
        <KVPair orientation="vertical" label="Customization ID" value={customization.id} />
        <KVPair
          orientation="vertical"
          label="Output Model"
          value={customization.spec?.output?.name ?? '-'}
        />
        <KVPair
          orientation="vertical"
          label="Base Model"
          value={getBaseModel(customization) || '-'}
        />
        <KVPair
          orientation="vertical"
          label="Created"
          value={customization.created_at ? formatAbsoluteTimestamp(customization.created_at) : '-'}
        />
        <KVPair
          orientation="vertical"
          label="Owner"
          value={
            customization.ownership?.created_by ? String(customization.ownership.created_by) : '-'
          }
        />
        <KVPair
          orientation="vertical"
          label="Description"
          value={customization.description || '-'}
        />
        {telemetry.checkpointPath && (
          <KVPair
            orientation="vertical"
            label="Latest Checkpoint"
            value={telemetry.checkpointPath}
            truncate
          />
        )}
        {isGrpoJob(customization) && <GrpoRunConfigPairs spec={customization.spec} />}
      </Grid>
    </Stack>
  </Panel>
);

/** A fragment, not its own grid, so these share the columns the rows above them are aligned to. */
const GrpoRunConfigPairs: FC<{ spec: RlJobOutput & { training: RlGRPOTraining } }> = ({ spec }) => {
  const config = getGrpoRunConfig(spec);
  return (
    <>
      <KVPair orientation="vertical" label="Environment" value={config.environment} truncate />
      <KVPair orientation="vertical" label="Prompt Dataset" value={config.promptDataset} truncate />
      <KVPair orientation="vertical" label="Training Backend" value={config.trainingBackend} />
      <KVPair orientation="vertical" label="Parallelism" value={config.parallelism} />
      <KVPair orientation="vertical" label="Generation" value={config.generation} />
      <KVPair orientation="vertical" label="Sequence Packing" value={config.sequencePacking} />
    </>
  );
};
