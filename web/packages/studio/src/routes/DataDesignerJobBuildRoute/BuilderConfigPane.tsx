// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Text } from '@nvidia/foundations-react-core';
import { ColumnConfigPanel } from '@studio/components/ColumnConfigPanel';
import { ModelConfigPanel } from '@studio/components/ModelConfigPanel';
import type { FC } from 'react';

export interface BuilderConfigPaneProps {
  selectedColumnId: string | null;
  selectedModelId: string | null;
  workspace: string;
  onColumnRemove: () => void;
  onColumnClose: () => void;
  onModelRemove: () => void;
  onModelClose: () => void;
}

export const BuilderConfigPane: FC<BuilderConfigPaneProps> = ({
  selectedColumnId,
  selectedModelId,
  workspace,
  onColumnRemove,
  onColumnClose,
  onModelRemove,
  onModelClose,
}) => (
  <div className="w-[240px] shrink-0 border-l border-base bg-surface-base">
    {selectedColumnId ? (
      <ColumnConfigPanel
        columnId={selectedColumnId}
        onRemove={onColumnRemove}
        onClose={onColumnClose}
      />
    ) : selectedModelId ? (
      <ModelConfigPanel
        modelId={selectedModelId}
        workspace={workspace}
        onRemove={onModelRemove}
        onClose={onModelClose}
      />
    ) : (
      <Flex align="center" justify="center" className="h-full p-density-lg">
        <Text kind="body/regular/sm" className="text-secondary text-center">
          Select a column or model to configure it, or add one from the left.
        </Text>
      </Flex>
    )}
  </div>
);
