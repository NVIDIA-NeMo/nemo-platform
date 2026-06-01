// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { creatorToIcon } from '@nemo/common/src/constants/modelMetadata';
import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import {
  useFilesListFilesetFiles,
  useFilesRetrieveFileset,
} from '@nemo/sdk/generated/platform/api';
import {
  Flex,
  PageHeader,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { isModelDetailTab, ModelDetailTab } from '@studio/routes/ModelDetailRoute/constants';
import { FilesTab } from '@studio/routes/ModelDetailRoute/FilesTab';
import { ModelCardTab } from '@studio/routes/ModelDetailRoute/ModelCardTab';
import { getModelSource, isRootReadme } from '@studio/routes/ModelDetailRoute/utils';
import { getWorkspaceFilesetsRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import type { FC } from 'react';

export const ModelDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { modelName } = useRequiredPathParams([ROUTE_PARAMS.modelName]);
  const modelId = getEntityReference({ namespace: workspace, name: modelName });

  const { getQueryParam, setQueryParam } = useQueryParams();
  const tabFromUrl = getQueryParam(QUERY_PARAMETERS.tab) || undefined;

  useBreadcrumbs({
    items: [
      { href: getWorkspaceFilesetsRoute(workspace), slotLabel: 'Filesets' },
      { slotLabel: modelName },
    ],
  });

  const queryEnabled = Boolean(workspace && modelName);
  const {
    data: filesResponse,
    isPending: isFilesPending,
    isFetching: isFilesFetching,
    isError: isFilesError,
  } = useFilesListFilesetFiles(workspace, modelName, undefined, {
    query: { enabled: queryEnabled },
  });
  const files = filesResponse?.data;

  const {
    data: fileset,
    isPending: isFilesetPending,
    isError: isFilesetError,
  } = useFilesRetrieveFileset(workspace, modelName, {
    query: { enabled: queryEnabled },
  });

  const hasReadme = files?.some(isRootReadme) ?? false;
  const defaultTab = hasReadme ? ModelDetailTab.Card : ModelDetailTab.Files;
  const currentTab: ModelDetailTab = isModelDetailTab(tabFromUrl) ? tabFromUrl : defaultTab;

  const source = fileset ? getModelSource(fileset) : undefined;
  const description = source ? (
    <Flex gap="density-sm" align="center">
      {creatorToIcon(source.creatorSlug, { className: 'w-4 h-4 flex-shrink-0' })}
      <span>{source.path}</span>
    </Flex>
  ) : undefined;

  const handleTabChange = (value: string) => {
    if (isModelDetailTab(value)) {
      setQueryParam(QUERY_PARAMETERS.tab, value);
    }
  };

  if (isFilesPending || isFilesetPending) {
    return <Loading description="Loading model..." />;
  }

  if (isFilesetError || !fileset) {
    return (
      <AccessibleTitle title={`Model ${modelName}`}>
        <Stack className="w-full h-full min-h-0 p-density-2xl" gap="density-xl">
          <PageHeader slotHeading={modelName} />
          <Text className="text-feedback-danger">Failed to load model.</Text>
        </Stack>
      </AccessibleTitle>
    );
  }

  return (
    <AccessibleTitle title={`Model ${modelName}`}>
      <Stack className="w-full h-full min-h-0 p-density-2xl" gap="density-xl">
        <PageHeader slotHeading={modelName} slotDescription={description} />
        <TabsRoot
          className="flex-1 min-h-0 flex flex-col"
          value={currentTab}
          onValueChange={handleTabChange}
        >
          <TabsList>
            <TabsTrigger value={ModelDetailTab.Card}>Model Card</TabsTrigger>
            <TabsTrigger value={ModelDetailTab.Files}>Files</TabsTrigger>
          </TabsList>

          <TabsContent value={ModelDetailTab.Card} className="p-0 flex-1 min-h-0 overflow-auto">
            <ModelCardTab
              workspace={workspace}
              modelName={modelName}
              fileset={fileset}
              files={files}
              isFilesError={isFilesError}
            />
          </TabsContent>

          <TabsContent value={ModelDetailTab.Files} className="p-0 flex-1 min-h-0">
            <FilesTab
              workspace={workspace}
              modelName={modelName}
              modelId={modelId}
              files={files}
              isFilesError={isFilesError}
              isFilesFetching={isFilesFetching}
            />
          </TabsContent>
        </TabsRoot>
      </Stack>
    </AccessibleTitle>
  );
};
