// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { PlatformJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { useDataDesignerGetCreateJob } from '@nemo/sdk/generated/data-designer/api';
import { Button, Card, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { JobOutputFilesetSection } from '@studio/routes/DataDesignerJobDetailsRoute/JobOutputFilesetSection';
import { getDataDesignerJobListRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { ArrowLeft } from 'lucide-react';
import { FC } from 'react';
import { Link } from 'react-router-dom';

export const DataDesignerJobDetailsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { dataDesignerJobName } = useRequiredPathParams([ROUTE_PARAMS.dataDesignerJobName]);

  const {
    data: job,
    isLoading,
    isError,
    refetch,
  } = useDataDesignerGetCreateJob(workspace, dataDesignerJobName, {
    query: {
      refetchInterval: (query) => {
        const status = query.state.data?.status;
        const isTerminated = status && PlatformJobTerminalStatuses.includes(status);
        return isTerminated ? false : 3000;
      },
    },
  });

  useBreadcrumbs({
    items: [
      {
        href: getDataDesignerJobListRoute(workspace),
        slotLabel: 'Data Designer',
      },
      {
        slotLabel: job?.name ?? dataDesignerJobName,
      },
    ],
  });

  if (isLoading && !job) {
    return <Loading description="Loading job..." />;
  }

  if (isError || !job) {
    return (
      <AccessibleTitle title={`Data Designer Job - ${dataDesignerJobName}`}>
        <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
          <ErrorMessage
            header="Failed to load job"
            message="The job could not be loaded. It may have been deleted or you may not have access."
            slotFooter={
              <Button type="button" kind="tertiary" onClick={() => refetch()}>
                Retry
              </Button>
            }
          />
          <Button asChild kind="secondary">
            <Link to={getDataDesignerJobListRoute(workspace)}>
              <ArrowLeft /> Back to Data Designer
            </Link>
          </Button>
        </Stack>
      </AccessibleTitle>
    );
  }

  return (
    <AccessibleTitle title={`Data Designer Job - ${job.name}`}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <Button asChild kind="secondary">
          <Link to={getDataDesignerJobListRoute(workspace)}>
            <ArrowLeft /> Back to Data Designer
          </Link>
        </Button>

        <Card>
          <Stack gap="density-lg">
            <Text kind="body/bold/2xl">{job.name}</Text>
            {job.description && (
              <Text kind="body/regular/md" className="text-muted">
                {job.description}
              </Text>
            )}
            <Stack direction="row" gap="density-md" align="center">
              <Text kind="label/semibold/md">Status:</Text>
              {job.status ? <StatusBadge status={job.status} /> : null}
            </Stack>
            {job.created_at && (
              <Text kind="body/regular/sm" className="text-muted">
                Created: {new Date(job.created_at).toLocaleString()}
              </Text>
            )}
            {job.updated_at && (
              <Text kind="body/regular/sm" className="text-muted">
                Updated: {new Date(job.updated_at).toLocaleString()}
              </Text>
            )}
          </Stack>
        </Card>

        <JobOutputFilesetSection workspace={workspace} jobName={dataDesignerJobName} job={job} />
      </Stack>
    </AccessibleTitle>
  );
};
