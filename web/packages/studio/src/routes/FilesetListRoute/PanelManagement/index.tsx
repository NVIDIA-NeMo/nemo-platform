// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { useFilesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import { DatasetFileManagementSidePanel } from '@studio/components/DatasetFileManagementSidePanel';
import { FilesetFilePreviewPanel } from '@studio/components/FilesetFilePreviewPanel';
import { ROUTE_PARAMS, ROUTES } from '@studio/constants/routes';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { getFilesetDetailsRoute, getFilesetFileRoute } from '@studio/routes/utils';
import { FC, useEffect, useState } from 'react';
import { generatePath, useNavigate, useParams } from 'react-router-dom';

interface PanelManagementProps {
  workspace: string;
}

/**
 * Manages the dataset and file preview panels using the animation pattern.
 *
 * This component handles:
 * - URL param reading and syncing
 * - Animation state management
 * - Panel open/close animations
 * - Dataset file fetching
 * - Navigation handlers for both panels
 */
export const PanelManagement: FC<PanelManagementProps> = ({ workspace }) => {
  const navigate = useNavigate();
  const { getQueryParam } = useQueryParams();

  // ==========================================
  // URL PARAMS & ANIMATION STATE
  // ==========================================

  // 1. Read URL params
  const {
    [ROUTE_PARAMS.filesetId]: datasetIdEncoded,
    [ROUTE_PARAMS.filePathEncoded]: filePathFromUrl,
  } = useParams();

  const datasetIdFromUrl = datasetIdEncoded ? decodeURIComponent(datasetIdEncoded) : undefined;
  const currentFolder = getQueryParam(QUERY_PARAMETERS.filesetFolder);

  // 2. Animation state (holds values during close animations)
  const [animatingDatasetId, setAnimatingDatasetId] = useState<string | undefined>();
  const [animatingFilePath, setAnimatingFilePath] = useState<string | undefined>();

  // 3. Open state (controls animations)
  const [isDatasetPanelOpen, setIsDatasetPanelOpen] = useState(false);
  const [isFilePanelOpen, setIsFilePanelOpen] = useState(false);

  // 4. Sync URL params to animating state
  useEffect(() => {
    if (datasetIdFromUrl) setAnimatingDatasetId(datasetIdFromUrl);
  }, [datasetIdFromUrl]);

  useEffect(() => {
    if (filePathFromUrl) setAnimatingFilePath(filePathFromUrl);
  }, [filePathFromUrl]);

  // 5. Sync open state with URL (triggers animations)
  useEffect(() => {
    setIsDatasetPanelOpen(!!datasetIdFromUrl);
  }, [datasetIdFromUrl]);

  useEffect(() => {
    setIsFilePanelOpen(!!filePathFromUrl);
  }, [filePathFromUrl]);

  // 6. Determine panel visibility
  const showDatasetPanel = !!(datasetIdFromUrl || animatingDatasetId);
  const showFilePanel = !!(filePathFromUrl || animatingFilePath);

  // ==========================================
  // DATASET PANEL LOGIC
  // ==========================================

  // Parse dataset info from URL
  const datasetFullName = animatingDatasetId || '';
  const { workspace: datasetworkspace, name: datasetName } = getPartsFromReference(datasetFullName);

  // Fetch dataset files
  const {
    data: filesResponse,
    isPending: isFilesPending,
    isFetching: isFilesFetching,
  } = useFilesListFilesetFiles(datasetworkspace || '', datasetName || '', undefined, {
    query: { enabled: showDatasetPanel },
  });
  const filesList = filesResponse?.data;

  // Dataset panel handlers
  const handleDatasetPanelClose = () => {
    navigate(generatePath(ROUTES.workspace.filesets, { workspace }));
  };

  const handleDatasetPanelOpenChange = (open: boolean) => {
    if (!open && !datasetIdFromUrl) {
      setAnimatingDatasetId(undefined); // Safe to unmount
    }
  };

  const handleFileSelect = (filePath: string) => {
    const to = getFilesetFileRoute(workspace, datasetFullName, filePath);
    navigate(to);
  };

  // ==========================================
  // FILE PANEL LOGIC
  // ==========================================

  const decodedFilePath = animatingFilePath ? decodeURIComponent(animatingFilePath) : '';

  // File panel handlers
  const handleFilePanelClose = () => {
    const folderPathFromFile = decodedFilePath.split('/').slice(0, -1).join('/');
    navigate(
      getFilesetDetailsRoute(
        workspace,
        encodeURIComponent(datasetFullName),
        encodeURIComponent(folderPathFromFile)
      )
    );
  };

  const handleFilePanelOutsideClick = () => {
    navigate(generatePath(ROUTES.workspace.filesets, { workspace }));
  };

  const handleDatasetClick = () => {
    navigate(getFilesetDetailsRoute(workspace, encodeURIComponent(datasetFullName)));
  };

  const handleFolderClick = (folderPath?: string) => {
    navigate(
      getFilesetDetailsRoute(
        workspace,
        encodeURIComponent(datasetFullName),
        folderPath ? encodeURIComponent(folderPath) : undefined
      )
    );
  };

  const handleFileDeleteSuccess = () => {
    // Navigate back to the folder or fileset root after deletion
    const folderPathFromFile = decodedFilePath.split('/').slice(0, -1).join('/');
    navigate(
      getFilesetDetailsRoute(
        workspace,
        encodeURIComponent(datasetFullName),
        encodeURIComponent(folderPathFromFile)
      )
    );
  };

  const handleFileRenameSuccess = (newPath: string) => {
    // Navigate to the renamed file
    navigate(getFilesetFileRoute(workspace, datasetFullName, newPath));
  };

  // ==========================================
  // RENDER
  // ==========================================

  return (
    <>
      {/* Dataset Panel - renders first (bottom layer) */}
      {showDatasetPanel && (
        <DatasetFileManagementSidePanel
          open={isDatasetPanelOpen}
          workspace={datasetworkspace || ''}
          datasetName={datasetName || ''}
          datasetId={datasetFullName}
          currentFolder={currentFolder}
          filesList={filesList}
          isLoading={isFilesPending}
          isFilesFetching={isFilesFetching}
          onFolderChange={handleFolderClick}
          onFileSelect={handleFileSelect}
          onClose={handleDatasetPanelClose}
          onOpenChange={handleDatasetPanelOpenChange}
        />
      )}

      {/* File Panel - renders last (top layer) */}
      {showFilePanel && (
        <FilesetFilePreviewPanel
          open={isFilePanelOpen}
          onCloseClick={handleFilePanelClose}
          onOutsideClick={handleFilePanelOutsideClick}
          workspace={datasetworkspace || ''}
          filesetName={datasetName || ''}
          filePath={decodedFilePath}
          onFilesetClick={handleDatasetClick}
          onFolderClick={handleFolderClick}
          onDeleteSuccess={handleFileDeleteSuccess}
          onRenameSuccess={handleFileRenameSuccess}
        />
      )}
    </>
  );
};
