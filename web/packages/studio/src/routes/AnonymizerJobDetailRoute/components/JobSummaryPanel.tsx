// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import type { RunJob } from '@nemo/sdk/generated/anonymizer/schema';
import { Banner, Grid, Panel, Stack } from '@nvidia/foundations-react-core';
import { EMPTY_FIELD_VALUE } from '@studio/constants/constants';
import { jobSource, jobStrategy } from '@studio/routes/AnonymizerJobDetailRoute/util';
import type { FC } from 'react';

interface JobSummaryPanelProps {
  readonly job: RunJob;
}

export const JobSummaryPanel: FC<JobSummaryPanelProps> = ({ job }) => {
  const errorMessage = job.error_details?.message as string | undefined;

  return (
    <Panel slotHeading="Job Details" elevation="high" density="compact">
      <Stack gap="density-xl">
        <Grid cols={{ base: 1, md: 2 }} gap="density-lg">
          <KVPair
            label="Status"
            value={job.status ? <StatusBadge status={job.status} /> : EMPTY_FIELD_VALUE}
          />
          <KVPair label="Strategy" value={jobStrategy(job) ?? EMPTY_FIELD_VALUE} />
          <KVPair
            label="Created"
            value={job.created_at ? <RelativeTime datetime={job.created_at} /> : EMPTY_FIELD_VALUE}
          />
          <KVPair
            label="Updated"
            value={job.updated_at ? <RelativeTime datetime={job.updated_at} /> : EMPTY_FIELD_VALUE}
          />
          <KVPair
            label="Created by"
            value={(job.ownership?.created_by as string | undefined) ?? EMPTY_FIELD_VALUE}
          />
        </Grid>
        <KVPair label="Source" value={jobSource(job) ?? EMPTY_FIELD_VALUE} />
        {errorMessage ? (
          <Banner kind="inline" status="error">
            {errorMessage}
          </Banner>
        ) : null}
      </Stack>
    </Panel>
  );
};
