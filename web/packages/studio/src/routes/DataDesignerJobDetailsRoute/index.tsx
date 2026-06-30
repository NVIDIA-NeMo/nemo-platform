// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import {
  Banner,
  Button,
  Flex,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { DataDesignerJobActionsMenu } from '@studio/components/DataDesignerJobActionsMenu';
import { Loading } from '@studio/components/Layouts/Loading';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { DataDesignerConfigPanel } from '@studio/routes/DataDesignerJobDetailsRoute/DataDesignerConfigPanel';
import { DatasetProfilerSection } from '@studio/routes/DataDesignerJobDetailsRoute/DatasetProfilerSection';
import { JobOutputFilesetSection } from '@studio/routes/DataDesignerJobDetailsRoute/JobOutputFilesetSection';
import { useDataDesignerJobFromRoute } from '@studio/routes/DataDesignerJobDetailsRoute/useDataDesignerJobFromRoute';
import { getDataDesignerJobListRoute } from '@studio/routes/utils';
import { ArrowLeft, FileJson } from 'lucide-react';
import { useState, type FC } from 'react';
import { Link, useNavigate } from 'react-router-dom';

export const DataDesignerJobDetailsRoute: FC = () => {
  const {
    workspace,
    jobName: dataDesignerJobName,
    job,
    isLoading,
    isError,
    refetch,
  } = useDataDesignerJobFromRoute();

  const navigate = useNavigate();
  const [isConfigPanelOpen, setIsConfigPanelOpen] = useState(false);
  const [cancelError, setCancelError] = useState<string | undefined>(undefined);

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
      <Stack className="h-full min-h-0" gap="density-2xl" padding="density-2xl">
        <Stack gap="density-md">
          <Flex gap="density-md" align="center" justify="between" className="flex-wrap">
            <Flex gap="density-md" align="center" className="flex-wrap">
              <Text kind="body/bold/2xl">{job.name}</Text>
              {job.status ? <StatusBadge status={job.status} /> : null}
            </Flex>
            <Flex gap="density-md" align="center">
              <Button type="button" kind="secondary" onClick={() => setIsConfigPanelOpen(true)}>
                <FileJson /> View config
              </Button>
              <DataDesignerJobActionsMenu
                job={job}
                onDeleted={() => navigate(getDataDesignerJobListRoute(workspace))}
                onCancelError={setCancelError}
              />
            </Flex>
          </Flex>
          {cancelError && (
            <Banner kind="inline" status="error">
              {cancelError}
            </Banner>
          )}
          {job.description && (
            <Text kind="body/regular/md" className="text-muted">
              {job.description}
            </Text>
          )}
          <Flex gap="density-lg" className="flex-wrap">
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
          </Flex>
        </Stack>

        <TabsRoot defaultValue="profile" className="flex min-h-0 w-full min-w-0 flex-1 flex-col">
          <TabsList>
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="output">Output files</TabsTrigger>
          </TabsList>

          <TabsContent value="profile" className="min-h-0 flex-1 overflow-y-auto px-0">
            <DatasetProfilerSection />
          </TabsContent>

          <TabsContent value="output" className="min-h-0 flex-1 overflow-y-auto px-0">
            <JobOutputFilesetSection />
          </TabsContent>
        </TabsRoot>
      </Stack>

      <DataDesignerConfigPanel
        open={isConfigPanelOpen}
        onClose={() => setIsConfigPanelOpen(false)}
      />
    </AccessibleTitle>
  );
};
