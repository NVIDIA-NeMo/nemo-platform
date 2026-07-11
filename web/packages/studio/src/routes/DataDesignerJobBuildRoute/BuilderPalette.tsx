// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { SegmentedControl } from '@nvidia/foundations-react-core';
import { AddColumnPalette } from '@studio/components/AddColumnPalette';
import type { AddColumnSelection } from '@studio/components/AddColumnPalette/types';
import { AddModelPalette } from '@studio/components/AddModelPalette';
import type { BuilderModel } from '@studio/routes/DataDesignerJobBuildRoute/models';
import type { PaletteTab } from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import type { FC } from 'react';

export interface BuilderPaletteProps {
  tab: PaletteTab;
  onTabChange: (tab: PaletteTab) => void;
  models: BuilderModel[];
  selectedModelId: string | null;
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels?: boolean;
  onAddColumn: (selection: AddColumnSelection) => void;
  onAddModel: (selection: ModelSelection, provider: string) => void;
  onSelectModel: (id: string | null) => void;
}

// Tabs only swap what you're adding — column and model configs both open in the right pane.
export const BuilderPalette: FC<BuilderPaletteProps> = ({
  tab,
  onTabChange,
  models,
  selectedModelId,
  modelGroups,
  isLoadingModels,
  onAddColumn,
  onAddModel,
  onSelectModel,
}) => (
  <aside className="flex w-[240px] shrink-0 flex-col gap-density-lg border-r border-base p-density-lg">
    <SegmentedControl
      size="tiny"
      className="w-full shrink-0"
      value={tab}
      onValueChange={(value) => onTabChange(value as PaletteTab)}
      items={[
        { value: 'columns', children: 'Columns' },
        { value: 'models', children: 'Models' },
      ]}
    />
    <div className="min-h-0 flex-1">
      {tab === 'columns' ? (
        <AddColumnPalette onAddColumn={onAddColumn} />
      ) : (
        <AddModelPalette
          models={models}
          selectedId={selectedModelId}
          modelGroups={modelGroups}
          isLoadingModels={isLoadingModels}
          onAddModel={onAddModel}
          onSelectModel={onSelectModel}
        />
      )}
    </div>
  </aside>
);
