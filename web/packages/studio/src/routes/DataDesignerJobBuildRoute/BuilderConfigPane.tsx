// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { Flex, Text } from '@nvidia/foundations-react-core';
import { ColumnConfigPanel } from '@studio/components/ColumnConfigPanel';
import { ModelConfigPanel } from '@studio/components/ModelConfigPanel';
import type { BuilderColumn } from '@studio/routes/DataDesignerJobBuildRoute/columns';
import type {
  BuilderModel,
  BuilderModelPatch,
} from '@studio/routes/DataDesignerJobBuildRoute/models';
import type { FC } from 'react';

export interface BuilderConfigPaneProps {
  selectedColumn: BuilderColumn | null;
  selectedModel: BuilderModel | null;
  takenNames: Set<string>;
  takenAliases: Set<string>;
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels: boolean;
  onColumnChange: (patch: { name?: string; values?: Record<string, string> }) => void;
  onColumnRemove: () => void;
  onColumnClose: () => void;
  onModelChange: (patch: BuilderModelPatch) => void;
  onModelRemove: () => void;
  onModelClose: () => void;
}

export const BuilderConfigPane: FC<BuilderConfigPaneProps> = ({
  selectedColumn,
  selectedModel,
  takenNames,
  takenAliases,
  modelGroups,
  isLoadingModels,
  onColumnChange,
  onColumnRemove,
  onColumnClose,
  onModelChange,
  onModelRemove,
  onModelClose,
}) => (
  <div className="w-[240px] shrink-0 border-l border-base bg-surface-base">
    {selectedColumn ? (
      <ColumnConfigPanel
        column={selectedColumn}
        takenNames={takenNames}
        onChange={onColumnChange}
        onRemove={onColumnRemove}
        onClose={onColumnClose}
      />
    ) : selectedModel ? (
      <ModelConfigPanel
        model={selectedModel}
        takenAliases={takenAliases}
        modelGroups={modelGroups}
        isLoadingModels={isLoadingModels}
        onChange={onModelChange}
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
