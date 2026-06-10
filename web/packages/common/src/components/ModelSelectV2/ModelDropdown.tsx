// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelDropdownItem } from '@nemo/common/src/components/ModelSelectV2/ModelDropdownItem';
import { ModelDropdownSearch } from '@nemo/common/src/components/ModelSelectV2/ModelDropdownSearch';
import type { ModelSelection, ModelType } from '@nemo/common/src/components/ModelSelectV2/types';
import { creatorToIcon } from '@nemo/common/src/constants/modelMetadata';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { filterModel, isBaseModel } from '@nemo/common/src/utils/models';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  DropdownContent,
  DropdownHeading,
  DropdownRoot,
  DropdownSection,
  DropdownTrigger,
  Flex,
  SegmentedControl,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { ChevronDown, LoaderCircle } from 'lucide-react';
import { useMemo, useState, type FC } from 'react';

const MODEL_TYPE_ITEMS = [
  { value: 'custom', children: 'Custom Models' },
  { value: 'base', children: 'Base Models' },
];

const isCustomModel = (model: ModelEntity): boolean => !isBaseModel(model);

interface ModelDropdownProps {
  value: ModelSelection | null;
  onValueChange: (selection: ModelSelection) => void;
  groups: ModelWorkspaceGroup[];
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
  showModelTypeToggle?: boolean;
  defaultModelType?: ModelType;
  hideAdapters?: boolean;
  fullWidth?: boolean;
  size?: 'small' | 'medium' | 'large';
  open: boolean;
  onOpenChange: (open: boolean) => void;
  triggerDisplay?: 'name' | 'urn';
}

export const ModelDropdown: FC<ModelDropdownProps> = ({
  value,
  onValueChange,
  groups,
  loading = false,
  disabled = false,
  placeholder = 'Select a model',
  showModelTypeToggle = false,
  defaultModelType = 'custom',
  hideAdapters = false,
  fullWidth = false,
  size = 'medium',
  open,
  onOpenChange,
  triggerDisplay = 'name',
}) => {
  const [search, setSearch] = useState('');
  const [modelType, setModelType] = useState<ModelType>(defaultModelType);

  const selectedModel = useMemo(() => {
    if (!value) return undefined;
    return groups.flatMap((g) => g.models).find((m) => getURNFromNamedEntityRef(m) === value.model);
  }, [groups, value]);

  const filteredGroups = useMemo(() => {
    return groups
      .map((group) => {
        let models = group.models;

        // Apply model type filter
        if (showModelTypeToggle) {
          models = modelType === 'base' ? models.filter(isBaseModel) : models.filter(isCustomModel);
        }

        // Apply search filter
        if (search) {
          models = models.filter((m) => filterModel(m, search));
        }

        return { ...group, models };
      })
      .filter((group) => group.models.length > 0);
  }, [groups, showModelTypeToggle, modelType, search]);

  const handleSelect = (selection: ModelSelection) => {
    onValueChange(selection);
    onOpenChange(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      setSearch('');
    }
  };

  const triggerLabel = selectedModel
    ? triggerDisplay === 'urn'
      ? `${selectedModel.workspace}/${selectedModel.name?.split('@')[0] ?? selectedModel.name}`
      : (selectedModel.name?.split('@')[0] ?? selectedModel.name)
    : // A value can be set before its entity is found in `groups` (e.g. a model
      // seeded from an agent that isn't in this workspace's list). Surface the
      // URN rather than the misleading "no selection" placeholder.
      value && triggerDisplay === 'urn'
      ? value.model
      : placeholder;

  const triggerTextKind = size === 'small' ? 'label/regular/sm' : 'label/regular/md';

  return (
    <DropdownRoot open={open} onOpenChange={handleOpenChange}>
      <DropdownTrigger
        asChild
        showChevron={false}
        className={fullWidth ? 'flex-1 w-full min-w-0' : undefined}
      >
        <Button
          kind="secondary"
          size={size}
          disabled={disabled}
          aria-label="Select a model"
          data-testid="model-select-v2-trigger"
          className="overflow-hidden !border-[var(--border-color-interaction-base)] !bg-[var(--background-color-interaction-base)] hover:!border-[var(--border-color-interaction-hover)] [&[data-state=open]]:!border-[var(--border-color-interaction-selected)]"
        >
          <Flex
            align="center"
            gap="density-sm"
            className={`min-w-0 ${fullWidth ? 'w-full justify-between' : ''}`}
          >
            <Flex align="center" gap="density-sm" className="min-w-0 flex-1">
              {selectedModel &&
                creatorToIcon(selectedModel.workspace ?? '', {
                  className: 'text-base flex-shrink-0',
                })}
              {loading ? (
                <>
                  <LoaderCircle size={16} className="animate-spin flex-shrink-0" />
                  <Text kind={triggerTextKind} className="truncate">
                    {placeholder}
                  </Text>
                </>
              ) : (
                <Text kind={triggerTextKind} className="truncate">
                  {triggerLabel}
                </Text>
              )}
            </Flex>
            <ChevronDown
              size={16}
              className={`flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
            />
          </Flex>
        </Button>
      </DropdownTrigger>
      <DropdownContent
        align="start"
        side="bottom"
        data-testid="model-select-v2-content"
        className="min-w-[360px]"
        style={{ width: 360 }} // eslint-disable-line no-restricted-syntax -- KUI DropdownContent needs explicit width
      >
        <ModelDropdownSearch value={search} onChange={setSearch} />
        {showModelTypeToggle && (
          <Flex className="px-2 pb-2 w-full">
            <SegmentedControl
              className="w-full"
              value={modelType}
              items={MODEL_TYPE_ITEMS}
              onValueChange={(val: string) => setModelType(val as ModelType)}
            />
          </Flex>
        )}
        <Stack className="overflow-auto max-h-[300px] w-full">
          {filteredGroups.length > 0 ? (
            filteredGroups.map((group) => (
              <DropdownSection key={group.workspace}>
                <DropdownHeading>
                  <Flex gap="density-sm" align="center">
                    {creatorToIcon(group.workspace, { className: 'text-base' })}
                    <Text>{group.workspace}</Text>
                  </Flex>
                </DropdownHeading>
                {group.models.map((model) => (
                  <ModelDropdownItem
                    key={getURNFromNamedEntityRef(model)}
                    model={model}
                    value={value}
                    onSelect={handleSelect}
                    hideAdapters={hideAdapters}
                  />
                ))}
              </DropdownSection>
            ))
          ) : (
            <DropdownSection>
              <DropdownHeading>
                <Text>{loading ? 'Loading models...' : 'No models found'}</Text>
              </DropdownHeading>
            </DropdownSection>
          )}
        </Stack>
      </DropdownContent>
    </DropdownRoot>
  );
};
