// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TableExpandableCellState } from '@nemo/common/src/components/DataView/TableExpandableCell';
import { Button, Flex, Modal, Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

interface ExpandedCellModalProps {
  readonly cell: TableExpandableCellState | null;
  readonly onClose: () => void;
}

export const ExpandedCellModal: FC<ExpandedCellModalProps> = ({ cell, onClose }) => (
  <Modal
    open={cell !== null}
    onOpenChange={(open) => {
      if (!open) onClose();
    }}
    slotHeading={cell?.title ?? 'Cell Content'}
    className="w-[90vw] max-w-[1000px]"
    slotFooter={
      <Flex justify="end" align="center" className="w-full">
        <Button kind="tertiary" onClick={onClose}>
          Close
        </Button>
      </Flex>
    }
  >
    <div className="max-h-[70vh] overflow-auto">
      <Text kind="body/regular/md" className="whitespace-pre-wrap">
        {cell?.content}
      </Text>
    </div>
  </Modal>
);
