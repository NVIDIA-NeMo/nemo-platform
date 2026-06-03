// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import {
  useFilesListFilesetFiles,
  useFilesRetrieveFileset,
} from '@nemo/sdk/generated/platform/api';
import { FilesetPurpose } from '@nemo/sdk/generated/platform/schema';
import {
  PageHeader,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { FilesetCard } from '@studio/components/FilesetCard';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import {
  FILESET_DETAIL_DEFAULT_TAB,
  FilesetDetailTab,
  isFilesetDetailTab,
} from '@studio/routes/FilesetDetailRoute/constants';
import { FilesTab } from '@studio/routes/FilesetDetailRoute/FilesTab';
import { getWorkspaceFilesetsRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import type { FC, ReactNode } from 'react';

const getCardTabLabel = (purpose: FilesetPurpose | undefined): string => {
  if (purpose === FilesetPurpose.dataset) return 'Dataset Card';
  if (purpose === FilesetPurpose.model) return 'Model Card';
  return 'Card';
};

/**
 * Dedicated full-page detail view for external filesets (HF / NGC / S3).
 *
 * Renders the same content the {@link DatasetFileManagementSidePanel} shows for
 * external filesets — a Card tab ({@link FilesetCard}: README + metadata) and a
 * Files tab ({@link FilesTab}) — but as a routed page instead of a slide-in
 * panel. The Fileset List routes external filesets here (behind
 * `VITE_FF_FILESET_DETAILS_ENABLED`); local filesets keep the side panel.
 */
export const FilesetDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { [ROUTE_PARAMS.filesetId]: filesetIdEncoded } = useRequiredPathParams([
    ROUTE_PARAMS.filesetId,
  ]);
  const filesetId = decodeURIComponent(filesetIdEncoded);
  const { workspace: filesetWorkspace, name: filesetName } = getPartsFromReference(filesetId);

  const { getQueryParam, setQueryParam } = useQueryParams();
  const tabFromUrl = getQueryParam(QUERY_PARAMETERS.tab) || undefined;
  const currentTab: FilesetDetailTab = isFilesetDetailTab(tabFromUrl)
    ? tabFromUrl
    : FILESET_DETAIL_DEFAULT_TAB;

  useBreadcrumbs({
    items: [
      { href: getWorkspaceFilesetsRoute(workspace), slotLabel: 'Filesets' },
      { slotLabel: filesetName },
    ],
  });

  // Files list drives the Card tab's README lookup; FilesTab fetches the same
  // query independently (React Query dedupes by key, so this is not a double
  // fetch).
  const { data: filesResponse, isPending: isFilesPending } = useFilesListFilesetFiles(
    filesetWorkspace,
    filesetName,
    undefined,
    { query: { enabled: !!filesetWorkspace && !!filesetName } }
  );
  const filesList = filesResponse?.data;

  const {
    data: fileset,
    isPending: isFilesetPending,
    isError: isFilesetError,
  } = useFilesRetrieveFileset(filesetWorkspace, filesetName, {
    query: { enabled: !!filesetWorkspace && !!filesetName },
  });

  const handleTabChange = (value: string) => {
    if (isFilesetDetailTab(value)) {
      setQueryParam(QUERY_PARAMETERS.tab, value);
    }
  };

  const renderCardContent = (): ReactNode => {
    return (
      <FilesetCard
        workspace={filesetWorkspace}
        filesetName={filesetName}
        fileset={fileset}
        files={filesList}
        isFilesLoading={isFilesetPending || isFilesPending}
        isFilesError={isFilesetError}
        testId="fileset-detail-card"
        metadataPanelTestId="fileset-detail-metadata"
      />
    );
  };

  return (
    <AccessibleTitle title={`Fileset ${filesetName}`}>
      <Stack className="w-full h-full min-h-0 p-density-2xl" gap="density-xl">
        <PageHeader className="p-0" slotHeading={filesetName} />
        <TabsRoot
          className="flex-1 min-h-0 flex flex-col"
          value={currentTab}
          onValueChange={handleTabChange}
        >
          <TabsList>
            <TabsTrigger value={FilesetDetailTab.Card}>
              {getCardTabLabel(fileset?.purpose)}
            </TabsTrigger>
            <TabsTrigger value={FilesetDetailTab.Files}>Files</TabsTrigger>
          </TabsList>

          <TabsContent value={FilesetDetailTab.Card} className="p-0 flex-1 min-h-0 overflow-hidden">
            {renderCardContent()}
          </TabsContent>

          <TabsContent value={FilesetDetailTab.Files} className="p-0 flex-1 min-h-0">
            <FilesTab filesetName={filesetName} filesetId={filesetId} />
          </TabsContent>
        </TabsRoot>
      </Stack>
    </AccessibleTitle>
  );
};
