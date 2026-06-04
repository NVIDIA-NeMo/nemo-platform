// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, Modal } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

export interface SharedSchemaConfirmModalProps {
  open: boolean;
  /** Number of files that reference the schema being edited. */
  referrerCount: number;
  /** Disable buttons while the save mutation is in flight. */
  isPending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const SharedSchemaConfirmModal: FC<SharedSchemaConfirmModalProps> = ({
  open,
  referrerCount,
  isPending,
  onConfirm,
  onCancel,
}) => (
  <Modal
    open={open}
    onOpenChange={(next) => {
      if (!next && !isPending) onCancel();
    }}
    slotHeading="Schema is shared"
    slotFooter={
      <Flex justify="end" gap="density-xs" align="center" className="w-full">
        <Button
          kind="tertiary"
          color="neutral"
          onClick={onCancel}
          disabled={isPending}
          data-testid="shared-schema-confirm-cancel"
        >
          Cancel
        </Button>
        <Button
          kind="primary"
          color="brand"
          onClick={onConfirm}
          disabled={isPending}
          data-testid="shared-schema-confirm-ok"
        >
          OK
        </Button>
      </Flex>
    }
  >
    <span data-testid="shared-schema-confirm-message">
      This schema is used by {referrerCount} {referrerCount === 1 ? 'file' : 'files'}. OK to
      proceed?
    </span>
  </Modal>
);
