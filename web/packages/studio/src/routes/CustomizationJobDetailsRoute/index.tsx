// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelsGetModel } from '@nemo/sdk/generated/platform/api';
import {
  PageHeader,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { CustomizationDetailsPanel } from '@studio/components/CustomizationDetailsPanel';
import { CustomizationFilesetDetailsPanel } from '@studio/components/CustomizationFilesetDetailsPanel';
import { Loading } from '@studio/components/Layouts/Loading';
import { ModelChat } from '@studio/components/ModelChat';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useCustomizationJob } from '@studio/hooks/useCustomizationJob';
import { useModelChatAvailability } from '@studio/hooks/useModelChatAvailability';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { DetailActions } from '@studio/routes/CustomizationJobDetailsRoute/DetailActions';
import { getCustomizationJobListRoute } from '@studio/routes/utils';
import { getDatasetUri } from '@studio/util/customizations';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { MessagesSquare } from 'lucide-react';
import { FC } from 'react';

export const CustomizationJobDetailsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { customizationJobName } = useRequiredPathParams([ROUTE_PARAMS.customizationJobName]);

  const { job, backend } = useCustomizationJob(workspace, customizationJobName);

  useBreadcrumbs({
    items: [
      {
        href: getCustomizationJobListRoute(workspace),
        slotLabel: 'Customizations',
      },
      {
        slotLabel: job?.id || '',
      },
    ],
  });

  const status = job?.status;
  const output_model = job?.spec.output?.name;
  const showChat = Boolean(output_model) && status === 'completed';

  // Fetch the output model entity so we can check deployment status
  const { data: outputModelEntity } = useModelsGetModel(workspace, output_model ?? '', undefined, {
    query: { enabled: showChat, retry: false },
  });

  const { modelChatStatus, isLoading: isChatStatusLoading } =
    useModelChatAvailability(outputModelEntity);

  return (
    <AccessibleTitle title={`Customization details for ${customizationJobName}`}>
      <Stack className="w-full p-density-2xl min-h-full" gap="density-xl">
        <PageHeader
          slotHeading="Customization Job"
          slotActions={
            <DetailActions
              model={output_model}
              status={status}
              backend={backend}
              name={customizationJobName}
            />
          }
        />
        <TabsRoot className="flex-1" defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            {output_model && status === 'completed' && (
              <TabsTrigger value="chat">
                <MessagesSquare />
                Chat with your Model
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="overview" className="p-0">
            <Stack className="w-full" gap="density-xl">
              <CustomizationDetailsPanel
                customizationJobName={customizationJobName}
                workspace={workspace}
              />
              <CustomizationFilesetDetailsPanel filesetUri={getDatasetUri(job) || undefined} />
            </Stack>
          </TabsContent>

          {showChat && output_model && (
            <TabsContent value="chat" className="flex flex-1 justify-center p-0">
              {isChatStatusLoading ? (
                <Loading />
              ) : (
                <ModelChat
                  model={output_model}
                  workspace={workspace}
                  className="max-w-[768px]"
                  modelChatStatus={modelChatStatus}
                />
              )}
            </TabsContent>
          )}
        </TabsRoot>
      </Stack>
    </AccessibleTitle>
  );
};
