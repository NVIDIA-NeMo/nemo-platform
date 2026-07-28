// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { SegmentedControl } from '@nvidia/foundations-react-core';
import { AddColumnPalette } from '@studio/components/AddColumnPalette';
import type { AddColumnSelection } from '@studio/components/AddColumnPalette/types';
import { AddModelPalette } from '@studio/components/AddModelPalette';
import type {
  JobBuilderFormValues,
  PaletteTab,
} from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import type { FC } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

export interface BuilderPaletteProps {
  tab: PaletteTab;
  onTabChange: (tab: PaletteTab) => void;
  selectedModelId: string | null;
  workspace: string;
  onAddColumn: (selection: AddColumnSelection) => void;
  onAddModel: (selection: ModelSelection, provider: string) => void;
  onSelectModel: (id: string | null) => void;
}

// Tabs only swap what you're adding — column and model configs both open in the right pane.
export const BuilderPalette: FC<BuilderPaletteProps> = ({
  tab,
  onTabChange,
  selectedModelId,
  workspace,
  onAddColumn,
  onAddModel,
  onSelectModel,
}) => {
  const { control, getValues } = useFormContext<JobBuilderFormValues>();
  const models = useWatch({ control, name: 'models' });
  const hasSeedColumn = getValues('columns').some(
    (column) => column.option.columnType === 'seed-dataset'
  );
  const disabledColumnReasons = hasSeedColumn
    ? { 'seed-dataset': 'Only one seed dataset is supported per recipe.' }
    : undefined;

  return (
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
          <AddColumnPalette onAddColumn={onAddColumn} disabledReasons={disabledColumnReasons} />
        ) : (
          <AddModelPalette
            models={models}
            selectedId={selectedModelId}
            workspace={workspace}
            onAddModel={onAddModel}
            onSelectModel={onSelectModel}
          />
        )}
      </div>
    </aside>
  );
};
