// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelSelectV2 } from '@nemo/common/src/components/ModelSelectV2/ModelSelectV2';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { CardIconBadge, SelectableCard } from '@studio/components/common/SelectableCard';
import {
  type BuilderModel,
  providerForModel,
} from '@studio/routes/DataDesignerJobBuildRoute/models';
import { Cpu } from 'lucide-react';
import type { FC } from 'react';

export interface AddModelPaletteProps {
  /** The models currently configured for this job. */
  models: BuilderModel[];
  /** The model currently open for editing, if any. */
  selectedId?: string | null;
  /** Platform models to choose from, grouped by workspace. */
  modelGroups: ModelWorkspaceGroup[];
  /** Whether the platform model list is still loading. */
  isLoadingModels?: boolean;
  /**
   * Adds a model config seeded from the picked platform model (with its resolved provider)
   * and opens it for editing.
   */
  onAddModel: (selection: ModelSelection, provider: string) => void;
  /** Opens an existing model config for editing. */
  onSelectModel: (id: string) => void;
  className?: string;
}

/**
 * "Models" palette for the Data Designer recipe builder — the sibling of the
 * {@link AddColumnPalette} behind the aside's segmented control.
 *
 * A {@link ModelSelectV2} at the top adds a model to the job config: picking a platform
 * model appends a config seeded from it and opens it in the right-hand config panel.
 * Existing models are listed below as keyboard-activatable {@link SelectableCard}s
 * (matching the column palette's look); activating one selects it for editing. The models
 * it lists are the same ones an LLM column's `model_alias` field references, so they live
 * in — and submit as part of — the one job config.
 */
export const AddModelPalette: FC<AddModelPaletteProps> = ({
  models,
  selectedId,
  modelGroups,
  isLoadingModels,
  onAddModel,
  onSelectModel,
  className,
}) => (
  <Stack gap="density-lg" className={`flex h-full min-h-0 flex-col ${className ?? ''}`}>
    <Stack gap="density-xxs" className="shrink-0">
      <Text kind="body/bold/md">Models</Text>
      <Text kind="body/regular/xs" className="text-secondary">
        Referenced by LLM columns via their model alias
      </Text>
    </Stack>

    {/* Picking a model adds it to the job config; the selector resets to its placeholder. */}
    <div className="shrink-0">
      <ModelSelectV2
        value={null}
        onValueChange={(selection) =>
          onAddModel(selection, providerForModel(modelGroups, selection.model))
        }
        groups={modelGroups}
        loading={isLoadingModels}
        placeholder="Add a model"
        fullWidth
        dropdownSide="bottom"
        aria-label="Add a model"
      />
    </div>

    <Stack gap="1.5" className="min-h-0 flex-1 overflow-y-auto">
      {models.length === 0 ? (
        <Text kind="body/regular/sm" className="text-secondary">
          No models yet. Add one to reference it from an LLM column.
        </Text>
      ) : (
        models.map((model) => (
          <SelectableCard
            key={model.id}
            title={model.alias || 'Untitled model'}
            subtitle={model.model || 'No model set'}
            selected={model.id === selectedId}
            onActivate={() => onSelectModel(model.id)}
            className="w-full"
            leading={
              <CardIconBadge>
                <Cpu size={15} className="text-accent-teal" aria-hidden />
              </CardIconBadge>
            }
          />
        ))
      )}
    </Stack>
  </Stack>
);
