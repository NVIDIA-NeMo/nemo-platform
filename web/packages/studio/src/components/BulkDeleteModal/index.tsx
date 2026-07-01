// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { useState } from 'react';

export interface BulkDeleteModalProps<T> {
  /** Items to delete. */
  items: T[];
  /** Whether the modal is open. */
  open: boolean;
  /**
   * Called when the user confirms. Should perform all deletions and throw on
   * failure — the generic surfaces the thrown message as inline error text.
   */
  onDelete: (items: T[]) => Promise<void>;
  /**
   * Modal title. Pass a function to derive it from the count, e.g.
   *   (count) => `Delete ${count} Job${count !== 1 ? 's' : ''}`
   */
  title: string | ((count: number) => string);
  /** Called on both successful delete AND user cancel. */
  onClose: () => void;
}

export const BulkDeleteModal = <T,>({
  items,
  open,
  onDelete,
  title,
  onClose,
}: BulkDeleteModalProps<T>) => {
  const [deleteError, setDeleteError] = useState<string | undefined>(undefined);

  const resolvedTitle = typeof title === 'function' ? title(items.length) : title;

  const handleDelete = async (): Promise<boolean> => {
    setDeleteError(undefined);
    try {
      await onDelete(items);
      onClose();
      return true;
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : 'Failed to delete');
      return false;
    }
  };

  const handleClose = () => {
    setDeleteError(undefined);
    onClose();
  };

  if (!open) return null;

  return (
    <DeleteConfirmationModal
      open={open}
      onDelete={handleDelete}
      simpleConfirm
      title={resolvedTitle}
      errorText={deleteError}
      onClose={handleClose}
    />
  );
};
