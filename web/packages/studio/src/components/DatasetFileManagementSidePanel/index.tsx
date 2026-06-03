// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FilesetPurpose,
  type FilesetFileOutput,
  type FilesetOutput,
} from '@nemo/sdk/generated/platform/schema';
import { Flex, SegmentedControl, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { DatasetBreadcrumbs } from '@studio/components/DatasetFileManagementSidePanel/DatasetBreadcrumbs';
import { FilesetCard } from '@studio/components/FilesetCard';
import { FilesetFileExplorer } from '@studio/components/filesets/FilesetFileExplorer';
import { FilesetSidePanelWrapper } from '@studio/components/filesets/FilesetSidePanelWrapper';
import { useEffect, useState, type FC, type ReactNode } from 'react';

enum SidePanelTab {
  Card = 'card',
  Files = 'files',
}

const getCardTabLabel = (purpose: FilesetPurpose | undefined): string => {
  if (purpose === FilesetPurpose.dataset) return 'Dataset Card';
  if (purpose === FilesetPurpose.model) return 'Model Card';
  return 'Card';
};

const isExternalFileset = (fileset: FilesetOutput | undefined): boolean =>
  fileset !== undefined && fileset.storage.type !== 'local';

export interface DatasetFileManagementSidePanelProps {
  /** Whether the sidepanel is open */
  open: boolean;
  /** Dataset workspace */
  workspace: string;
  /** Dataset name */
  datasetName: string;
  /** Full dataset identifier (workspace/name) */
  datasetId: string;
  /** Current folder path (from query param or state) */
  currentFolder?: string;
  /** All files in the dataset (for navigation and search) */
  filesList: FilesetFileOutput[] | undefined;
  /** Whether file list is loading */
  isLoading: boolean;
  /** Whether files are currently being fetched */
  isFilesFetching: boolean;
  /** Whether file list errored */
  isFilesError?: boolean;
  /** Fileset record (drives the Card tab) */
  fileset?: FilesetOutput;
  /** Whether the fileset record is loading */
  isFilesetLoading?: boolean;
  /** Whether the fileset record errored */
  isFilesetError?: boolean;
  /** Callback when folder path changes */
  onFolderChange: (folderPath?: string) => void;
  /** Callback when a file is selected for viewing */
  onFileSelect: (filePath: string) => void;
  /** Callback when sidepanel is closed */
  onClose: () => void;
  /** Callback when panel animation completes (for animation lifecycle management) */
  onOpenChange?: (open: boolean) => void;
}

/**
 * Reusable dataset file management sidepanel.
 *
 * For **external** filesets (HF / NGC / S3) the panel exposes a segmented
 * control with two views:
 *   - **Card** — renders {@link FilesetCard} (description + README from the
 *     fileset's root, plus a metadata sidebar).
 *   - **Files** — the existing {@link FilesetFileExplorer}.
 *
 * For **local** filesets there's no upstream README to show, so the switcher is
 * hidden entirely and the explorer renders directly inside the panel — the
 * pre-card UX.
 *
 * When the panel opens for an external fileset, **Card** is the default view;
 * once the user picks a view it's sticky for the lifetime of the panel.
 */
export const DatasetFileManagementSidePanel: FC<DatasetFileManagementSidePanelProps> = ({
  open,
  workspace,
  datasetName,
  datasetId,
  currentFolder,
  filesList,
  isLoading,
  isFilesFetching,
  isFilesError = false,
  fileset,
  isFilesetLoading = false,
  isFilesetError = false,
  onFolderChange,
  onFileSelect,
  onClose,
  onOpenChange,
}) => {
  // Tab selection is intentionally sticky once decided. We track the user's
  // explicit pick AND lock the auto-computed default on the first fileset
  // load per panel session. Without locking, a transient `fileset = undefined`
  // during state churn could flip `defaultTab` mid-animation and re-mount
  // tab content.
  const [userPickedTab, setUserPickedTab] = useState<SidePanelTab | undefined>(undefined);
  const [lockedDefaultTab, setLockedDefaultTab] = useState<SidePanelTab | undefined>(undefined);

  useEffect(() => {
    if (lockedDefaultTab !== undefined) return;
    if (!fileset) return;
    setLockedDefaultTab(isExternalFileset(fileset) ? SidePanelTab.Card : SidePanelTab.Files);
  }, [fileset, lockedDefaultTab]);

  // Reset both pieces of tab state whenever the panel opens for a different
  // fileset so each row click gets a fresh auto-default.
  useEffect(() => {
    setUserPickedTab(undefined);
    setLockedDefaultTab(undefined);
  }, [datasetId]);

  const showTabs = isFilesetLoading || isFilesetError || isExternalFileset(fileset);
  const activeTab = userPickedTab ?? lockedDefaultTab ?? SidePanelTab.Card;

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      onClose();
    }
    onOpenChange?.(isOpen);
  };

  const renderCardContent = (): ReactNode => {
    if (isFilesetLoading) {
      return (
        <Flex className="h-full min-h-0 px-density-xl" align="center" justify="center">
          <Spinner description="Loading card..." />
        </Flex>
      );
    }
    if (isFilesetError || !fileset) {
      return (
        <Flex className="h-full min-h-0 px-density-xl" align="center" justify="center">
          <Text className="text-feedback-danger">Failed to load fileset.</Text>
        </Flex>
      );
    }
    return (
      <Stack className="h-full min-h-0 px-density-xl pb-density-xl">
        <FilesetCard
          workspace={workspace}
          filesetName={datasetName}
          fileset={fileset}
          files={filesList}
          isFilesLoading={isLoading}
          isFilesError={isFilesError}
          testId="dataset-side-panel-card"
          metadataPanelTestId="dataset-side-panel-metadata"
        />
      </Stack>
    );
  };

  const renderExplorer = (): ReactNode => (
    <FilesetFileExplorer
      workspace={workspace}
      datasetName={datasetName}
      datasetId={datasetId}
      currentFolder={currentFolder}
      filesList={filesList}
      isLoading={isLoading}
      isFilesFetching={isFilesFetching}
      onFileSelect={onFileSelect}
      enabled={open}
    />
  );

  return (
    <FilesetSidePanelWrapper
      open={open}
      onOpenChange={handleOpenChange}
      slotHeading={
        <DatasetBreadcrumbs
          datasetName={datasetName}
          currentFolder={currentFolder}
          onFolderChange={onFolderChange}
        />
      }
    >
      <Stack className="h-full min-h-0 w-full ">
        {showTabs ? (
          <>
            <div className="shrink-0 px-density-xl py-density-md">
              <SegmentedControl
                className="w-full"
                value={activeTab}
                onValueChange={(value) => setUserPickedTab(value as SidePanelTab)}
                items={[
                  { value: SidePanelTab.Card, children: getCardTabLabel(fileset?.purpose) },
                  { value: SidePanelTab.Files, children: 'Files' },
                ]}
              />
            </div>

            <Stack
              className={
                activeTab === SidePanelTab.Card
                  ? 'min-h-0 flex-1 overflow-hidden'
                  : 'min-h-0 flex-1 overflow-y-auto'
              }
            >
              {activeTab === SidePanelTab.Card ? renderCardContent() : renderExplorer()}
            </Stack>
          </>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">{renderExplorer()}</div>
        )}
      </Stack>
    </FilesetSidePanelWrapper>
  );
};
