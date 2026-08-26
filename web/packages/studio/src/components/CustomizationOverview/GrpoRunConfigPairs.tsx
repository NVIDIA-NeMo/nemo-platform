// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import type { RlGRPOTraining, RlJobOutput } from '@nemo/sdk/generated/customizer/schema';
import { getGrpoRunConfig } from '@studio/util/customizations';
import type { FC } from 'react';

interface Props {
  spec: RlJobOutput & { training: RlGRPOTraining };
}

/** A fragment, not its own grid, so these share the columns the rows above them are aligned to. */
export const GrpoRunConfigPairs: FC<Props> = ({ spec }) => {
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
