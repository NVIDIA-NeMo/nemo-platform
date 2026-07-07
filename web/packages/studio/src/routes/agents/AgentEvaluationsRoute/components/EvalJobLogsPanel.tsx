// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LogViewer } from '@nemo/common/src/components/LogViewer';
import { useJobLogs } from '@nemo/common/src/hooks/useJobLogs';
import type { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import { Panel } from '@nvidia/foundations-react-core';
import { ScrollText } from 'lucide-react';
import { type FC } from 'react';

interface EvalJobLogsPanelProps {
  workspace: string;
  /** The evaluation job name. This is also the platform job name, so it maps
   *  straight to the ``/jobs/{name}/logs`` endpoint. */
  jobName: string;
  /** Drives polling: logs keep refetching while the job is non-terminal and
   *  stop once it reaches a terminal state. */
  jobStatus?: string;
}

/**
 * Chronological log stream for an evaluation job.
 *
 * The evaluate-agent step writes its logs as many individual per-record
 * parquet files (UUID filenames, no ordering in the name). The platform jobs
 * API merges those records and returns them sorted by their ``timestamp``
 * column, so we render that server-ordered stream directly rather than
 * downloading and re-sorting the raw files.
 */
export const EvalJobLogsPanel: FC<EvalJobLogsPanelProps> = ({ workspace, jobName, jobStatus }) => {
  const {
    data: logs,
    isLoading,
    total,
  } = useJobLogs({
    workspace,
    name: jobName,
    jobStatus: jobStatus as PlatformJobStatus | undefined,
    enabled: !!workspace && !!jobName,
  });

  return (
    <Panel
      slotHeading={total > 0 ? `Logs (${total})` : 'Logs'}
      slotIcon={<ScrollText />}
      elevation="high"
      density="compact"
    >
      <LogViewer
        logs={logs}
        isLoading={isLoading}
        downloadFilename={`${jobName}-logs.txt`}
        emptyMessage="No logs recorded for this evaluation job."
      />
    </Panel>
  );
};
