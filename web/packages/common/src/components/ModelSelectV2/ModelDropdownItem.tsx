// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelDetailsPanel } from '@nemo/common/src/components/ModelSelectV2/ModelDetailsPanel';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import type { Adapter, ModelEntity } from '@nemo/sdk/generated/platform/schema';
import {
  Divider,
  DropdownHeading,
  DropdownItem,
  DropdownSub,
  DropdownSubContent,
  DropdownSubTrigger,
  Flex,
  Text,
} from '@nvidia/foundations-react-core';
import { Check } from 'lucide-react';
import type { FC } from 'react';

interface ModelDropdownItemProps {
  model: ModelEntity;
  value: ModelSelection | null;
  onSelect: (selection: ModelSelection) => void;
  hideAdapters?: boolean;
}

const formatDate = (dateString: string | undefined): string => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit' });
};

const ModelName: FC<{ name: string | undefined }> = ({ name }) => {
  const baseName = name?.split('@')[0];
  const version = name?.includes('@') ? name.split('@')[1] : undefined;

  return (
    <Flex className="w-full" align="center" justify="between">
      <Text className="truncate flex-1">{baseName}</Text>
      {version && (
        <Text
          className="text-secondary truncate ml-2 max-w-16 text-left"
          style={{ direction: 'rtl' }} // eslint-disable-line no-restricted-syntax -- RTL truncation for version suffix
        >
          {version}
        </Text>
      )}
    </Flex>
  );
};

const AdapterItem: FC<{
  adapter: Adapter;
  model: ModelEntity;
  modelUrn: string;
  isSelected: boolean;
  onSelect: (selection: ModelSelection) => void;
}> = ({ adapter, model, modelUrn, isSelected, onSelect }) => {
  return (
    <DropdownSub>
      <DropdownSubTrigger
        slotEnd={false}
        data-testid="model-dropdown-adapter-option"
        onSelect={() => onSelect({ model: modelUrn, adapter: adapter.name })}
      >
        <Flex className="w-full" align="center" justify="between" gap="density-md">
          <Flex align="center" gap="density-sm" className="min-w-0">
            {isSelected && <Check size={14} className="flex-shrink-0" />}
            <Text className="truncate">{adapter.name}</Text>
          </Flex>
          {adapter.created_at && (
            <Text className="text-secondary whitespace-nowrap" kind="body/regular/sm">
              {formatDate(adapter.created_at)}
            </Text>
          )}
        </Flex>
      </DropdownSubTrigger>
      {/* eslint-disable-next-line no-restricted-syntax -- KUI ignores Tailwind width classes */}
      <DropdownSubContent style={{ width: 360 }}>
        <ModelDetailsPanel model={model} adapter={adapter} />
      </DropdownSubContent>
    </DropdownSub>
  );
};

export const ModelDropdownItem: FC<ModelDropdownItemProps> = ({
  model,
  value,
  onSelect,
  hideAdapters = false,
}) => {
  const modelUrn = getURNFromNamedEntityRef(model)!;
  const hasAdapters = !hideAdapters && model.adapters && model.adapters.length > 0;

  if (!hasAdapters) {
    return (
      <DropdownSub>
        <DropdownSubTrigger
          slotEnd={false}
          data-testid="model-dropdown-item"
          onClick={() => onSelect({ model: modelUrn })}
        >
          <ModelName name={model.name} />
        </DropdownSubTrigger>
        {/* eslint-disable-next-line no-restricted-syntax -- KUI ignores Tailwind width classes */}
        <DropdownSubContent style={{ width: 360 }}>
          <ModelDetailsPanel model={model} />
        </DropdownSubContent>
      </DropdownSub>
    );
  }

  const sortedAdapters = [...model.adapters!].sort((a, b) => {
    if (!a.created_at || !b.created_at) return 0;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const isBaseSelected = value?.model === modelUrn && !value?.adapter;

  return (
    <DropdownSub>
      <DropdownSubTrigger data-testid="model-dropdown-item-with-adapters">
        <ModelName name={model.name} />
      </DropdownSubTrigger>
      {/* eslint-disable-next-line no-restricted-syntax -- KUI ignores Tailwind width classes */}
      <DropdownSubContent style={{ width: 360 }}>
        <DropdownHeading>Base Model</DropdownHeading>
        <DropdownItem
          data-testid="model-dropdown-base-option"
          onSelect={() => onSelect({ model: modelUrn })}
        >
          <Flex align="center" gap="density-sm">
            {isBaseSelected && <Check size={14} className="flex-shrink-0" />}
            <Text>{modelUrn}</Text>
          </Flex>
        </DropdownItem>
        <Divider />
        <DropdownHeading>Adapters</DropdownHeading>
        {sortedAdapters.map((adapter) => (
          <AdapterItem
            key={adapter.name}
            adapter={adapter}
            model={model}
            modelUrn={modelUrn}
            isSelected={value?.model === modelUrn && value?.adapter === adapter.name}
            onSelect={onSelect}
          />
        ))}
      </DropdownSubContent>
    </DropdownSub>
  );
};
