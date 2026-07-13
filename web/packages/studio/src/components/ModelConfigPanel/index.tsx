// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelSelectV2 } from '@nemo/common/src/components/ModelSelectV2/ModelSelectV2';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import type { InferenceParams } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, FormField, Stack, Text, TextInput } from '@nvidia/foundations-react-core';
import { CardIconBadge } from '@studio/components/common/SelectableCard';
import {
  type BuilderModel,
  type BuilderModelPatch,
  providerForModel,
  validateModelAlias,
} from '@studio/routes/DataDesignerJobBuildRoute/models';
import { Cpu, Trash2, X } from 'lucide-react';
import type { FC } from 'react';

export interface ModelConfigPanelProps {
  model: BuilderModel;
  takenAliases: Set<string>;
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels?: boolean;
  onChange: (patch: BuilderModelPatch) => void;
  onRemove: () => void;
  onClose: () => void;
}

/** Right-hand config panel for a model — sibling of ColumnConfigPanel, same inline layout. */
export const ModelConfigPanel: FC<ModelConfigPanelProps> = ({
  model,
  takenAliases,
  modelGroups,
  isLoadingModels,
  onChange,
  onRemove,
  onClose,
}) => {
  const aliasError = validateModelAlias(model.alias, takenAliases);
  const modelValue: ModelSelection | null = model.model ? { model: model.model } : null;

  const handleModelChange = (selection: ModelSelection) =>
    onChange({ model: selection.model, provider: providerForModel(modelGroups, selection.model) });
  const handleParamsChange = (params: Partial<InferenceParams>) =>
    onChange({ inferenceParams: params });

  return (
    <aside
      aria-label={`Configure ${model.alias || 'model'}`}
      className="flex h-full w-full flex-col bg-surface-base"
    >
      <Flex
        align="start"
        justify="between"
        gap="density-md"
        className="shrink-0 border-b border-base p-density-lg"
      >
        <Flex align="center" gap="density-sm" className="min-w-0">
          <CardIconBadge>
            <Cpu size={16} className="text-accent-teal" aria-hidden />
          </CardIconBadge>
          <Stack gap="density-xxs" className="min-w-0">
            <Text kind="body/bold/md" className="truncate">
              Model
            </Text>
            <Text kind="body/regular/xs" className="text-secondary truncate">
              Referenced by LLM columns via its alias
            </Text>
          </Stack>
        </Flex>
        <Button
          kind="tertiary"
          color="neutral"
          size="small"
          aria-label="Close model config"
          onClick={onClose}
        >
          <X size={16} aria-hidden />
        </Button>
      </Flex>

      <Stack gap="density-lg" padding="density-lg" className="min-h-0 flex-1 overflow-y-auto">
        <FormField
          slotLabel="Alias"
          required
          slotInfo="LLM columns reference this model via their model alias."
          status={model.alias && aliasError ? 'error' : undefined}
          slotError={model.alias ? (aliasError ?? undefined) : undefined}
        >
          <TextInput
            value={model.alias}
            onValueChange={(value) => onChange({ alias: value })}
            placeholder="e.g. default"
            attributes={{ Input: { 'aria-label': 'Model alias' } }}
          />
        </FormField>

        <FormField slotLabel="Model" required slotInfo="Model and inference parameters.">
          <ModelSelectV2
            value={modelValue}
            onValueChange={handleModelChange}
            groups={modelGroups}
            loading={isLoadingModels}
            placeholder="Select a model"
            showParams
            fullWidth
            dropdownSide="bottom"
            inferenceParams={model.inferenceParams}
            onInferenceParamsChange={handleParamsChange}
            aria-label="Model selector"
          />
        </FormField>
      </Stack>

      <Flex align="center" justify="start" className="shrink-0 border-t border-base p-density-lg">
        <Button kind="tertiary" color="danger" size="small" onClick={onRemove}>
          <Trash2 size={16} aria-hidden />
          Remove model
        </Button>
      </Flex>
    </aside>
  );
};
