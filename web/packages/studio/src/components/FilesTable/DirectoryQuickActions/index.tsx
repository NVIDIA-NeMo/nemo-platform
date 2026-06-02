// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { useDatasetDirectoryDelete } from '@studio/api/datasets/useDatasetDirectoryDelete';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { FileSystemDirectory } from '@studio/components/FilesTable/utils';
import { QuickActionsMenuRoot } from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { useSelectedDatasetId } from '@studio/hooks/useSelectedDatasetId';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { resolveDatasetFilePath } from '@studio/util/files';
import { FC, useState } from 'react';

interface Props {
  datasetId?: string;
  directory: FileSystemDirectory;
  /** When set (e.g. file side panel), overrides URL query folder for path resolution */
  currentFolder?: string;
}

export const DirectoryQuickActions: FC<Props> = ({ datasetId, directory, currentFolder }) => {
  const [openModal, setOpenModal] = useState<'delete'>();
  const toast = useToast();
  const datasetFullName = useSelectedDatasetId({ datasetId });
  const { workspace, name } = getPartsFromReference(datasetFullName);

  const { mutateAsync: deleteDirectory, error: deleteError } = useDatasetDirectoryDelete();
  const { getQueryParam } = useQueryParams();

  const folderFromQuery = getQueryParam(QUERY_PARAMETERS.filesetFolder);
  const path = resolveDatasetFilePath(
    directory.path,
    currentFolder ?? folderFromQuery ?? undefined
  );

  const handleDeleteDirectory = async () => {
    if (!workspace || !name) {
      toast.error('Failed to delete file: invalid dataset name');
      return false;
    }

    try {
      const response = await deleteDirectory({ workspace, datasetName: name, path });
      toast.success('Directory deleted successfully');
      return Boolean(response);
    } catch (error) {
      toast.error(
        `Failed to delete directory: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
      return false;
    }
  };

  const actions = [
    {
      label: 'Delete',
      onSelect: () => setOpenModal('delete'),
      danger: true,
    },
  ];

  return (
    <>
      <QuickActionsMenuRoot actions={actions} />
      <DeleteConfirmationModal
        open={openModal === 'delete'}
        onDelete={handleDeleteDirectory}
        simpleConfirm
        title="Delete Directory"
        errorText={deleteError?.message}
        onClose={() => setOpenModal(undefined)}
      />
    </>
  );
};
