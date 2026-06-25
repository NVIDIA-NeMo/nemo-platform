// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useFilesDeleteFileset } from '@nemo/sdk/generated/platform/api';
import type { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Button } from '@nvidia/foundations-react-core';
import { useMutateMany } from '@studio/api/common/useMutateMany';
import { invalidateDatasetCaches } from '@studio/api/datasets/invalidateDatasetCaches';
import { BulkDeleteModal as GenericBulkDeleteModal } from '@studio/components/BulkDeleteModal';
import { Trash } from 'lucide-react';
import { cloneElement, isValidElement, type FC, type ReactNode, useState } from 'react';

interface DatasetBulkDeleteModalProps {
  selectedDatasets: FilesetOutput[];
  onConfirmSuccess: () => void;
  /** Custom trigger element; when provided, used instead of the default Button */
  slotTrigger?: ReactNode;
}

export const DatasetBulkDeleteModal: FC<DatasetBulkDeleteModalProps> = ({
  selectedDatasets,
  onConfirmSuccess,
  slotTrigger,
}) => {
  const [open, setOpen] = useState(false);

  const { mutateAsync: deleteDataset } = useFilesDeleteFileset({
    mutation: {
      onSuccess: (_data, variables) => {
        invalidateDatasetCaches(variables.workspace, variables.name, ['list']);
      },
    },
  });
  const { mutateAsync: deleteDatasets } = useMutateMany(deleteDataset);

  const handleDelete = async (datasets: FilesetOutput[]) => {
    const datasetsToDelete = datasets.filter(
      (dataset): dataset is FilesetOutput & { workspace: string; name: string } =>
        !!(dataset.workspace && dataset.name)
    );
    await deleteDatasets(
      datasetsToDelete.map((dataset) => ({ workspace: dataset.workspace, name: dataset.name }))
    );
    onConfirmSuccess();
  };

  const openTrigger = () => setOpen(true);

  const trigger = isValidElement(slotTrigger) ? (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    cloneElement(slotTrigger as React.ReactElement<any>, { onClick: openTrigger })
  ) : (
    <Button kind="secondary" data-testid="bulk-delete-modal-trigger-button" onClick={openTrigger}>
      <Trash />
      Delete
    </Button>
  );

  return (
    <>
      {trigger}
      <GenericBulkDeleteModal
        items={selectedDatasets}
        open={open}
        onDelete={handleDelete}
        title={(count) => `Delete ${count} Dataset${count !== 1 ? 's' : ''}`}
        onClose={() => setOpen(false)}
      />
    </>
  );
};
