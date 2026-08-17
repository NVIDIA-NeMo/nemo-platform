// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ironSwarmListRuns, useIronSwarmCreateJob } from '@iron-swarm/generated/api';
import type { IronSwarmRun } from '@iron-swarm/generated/schema';
import { useToast } from '@iron-swarm/host';
import { getIronSwarmRunDetailsRoute, getIronSwarmRunListRoute } from '@iron-swarm/paths';
import { useNavigate } from 'react-router';

// Submit the war-game job for a manifest and open the run it creates. The service-driven job creates its
// run record shortly after it starts (linked by job_id), so we poll the newest runs for that link and
// navigate to the run detail; fall back to the runs list if it doesn't appear.
export const useRunWarGame = (workspace: string) => {
  const navigate = useNavigate();
  const toast = useToast();

  // The worker creates the run record right as the job starts, so we poll the newest runs for the one
  // linked to this job and jump to its Swarm tab the instant it appears. Poll snappily (0.5s) over a wide
  // window (~30s) so slow job starts still land on the run — only fall back to the list if it never shows.
  const openRunForJob = async (jobName: string): Promise<void> => {
    for (let attempt = 0; attempt < 60; attempt++) {
      const { data } = await ironSwarmListRuns(workspace, { sort: '-created_at', page_size: 20 });
      const run = (data as IronSwarmRun[] | undefined)?.find((r) => r.job_id === jobName);
      if (run?.name) {
        navigate(getIronSwarmRunDetailsRoute(workspace, run.name));
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    navigate(getIronSwarmRunListRoute(workspace));
  };

  return useIronSwarmCreateJob({
    mutation: {
      onSuccess: (job) => {
        toast.success('War-game started — opening the run…');
        void openRunForJob(job.name);
      },
      onError: () => toast.error('Failed to start the war-game.'),
    },
  });
};
