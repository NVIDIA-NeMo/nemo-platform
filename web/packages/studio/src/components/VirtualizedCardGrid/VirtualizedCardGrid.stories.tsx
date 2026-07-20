/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import type { ModelEntity, ModelSpec } from '@nemo/sdk/generated/platform/schema';
import { Flex, PageHeader, Select, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';
import { BaseModelCard } from '@studio/components/BaseModelCard';
import { VirtualizedCardGrid } from '@studio/components/VirtualizedCardGrid/index';
import { useCallback, useRef, useState, type ComponentProps, type FC } from 'react';

// ---------------------------------------------------------------------------
// Mock data generation
// ---------------------------------------------------------------------------

const MODEL_TEMPLATES = [
  { name: 'llama-3.1-8b-instruct', workspace: 'meta', params: 8e9, ctx: 8192, chat: true },
  { name: 'nemotron-nano-8b', workspace: 'nvidia', params: 8e9, ctx: 4096, chat: true },
  { name: 'mistral-7b-instruct-v0.3', workspace: 'mistralai', params: 7e9, ctx: 32768, chat: true },
  { name: 'gemma-2-9b-it', workspace: 'google', params: 9e9, ctx: 8192, chat: true },
  { name: 'phi-4', workspace: 'microsoft', params: 14e9, ctx: 16384, chat: false },
  { name: 'codellama-70b', workspace: 'meta', params: 70e9, ctx: 4096, chat: true },
  { name: 'nemotron-4-340b-instruct', workspace: 'nvidia', params: 340e9, ctx: 4096, chat: true },
  { name: 'mixtral-8x7b-instruct', workspace: 'mistralai', params: 47e9, ctx: 32768, chat: true },
] as const;

const DESCRIPTIONS = [
  'A large language model optimized for multilingual dialogue and instruction following.',
  'Compact, instruction-tuned model for efficient customization and deployment.',
  'Versatile model for code generation, reasoning, and general-purpose text tasks.',
  'Advanced reasoning model with strong math and science capabilities.',
  'Lightweight model designed for edge deployment with minimal resource requirements.',
  undefined,
];

const PROVIDERS = [
  ['default/nvidia-build'],
  ['default/nvidia-build', 'default/build'],
  ['default/build'],
  [],
];

function makeModel(index: number): ModelEntity {
  const template = MODEL_TEMPLATES[index % MODEL_TEMPLATES.length];
  const suffix =
    index >= MODEL_TEMPLATES.length ? `-v${Math.floor(index / MODEL_TEMPLATES.length) + 1}` : '';
  return {
    id: `model-${index}`,
    created_at: new Date(2025, 0, 1 + (index % 90)).toISOString(),
    updated_at: new Date(2025, 3, 1 + (index % 30)).toISOString(),
    name: `${template.name}${suffix}`,
    workspace: template.workspace,
    description: DESCRIPTIONS[index % DESCRIPTIONS.length],
    spec: {
      base_num_parameters: template.params,
      context_size: template.ctx,
      is_chat: template.chat,
    } as ModelSpec,
    model_providers: PROVIDERS[index % PROVIDERS.length],
  } as ModelEntity;
}

function generateModels(count: number): ModelEntity[] {
  return Array.from({ length: count }, (_, i) => makeModel(i));
}

const ALL_MODELS = generateModels(250);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SORT_OPTIONS = [
  { value: 'name', children: 'Alphabetical (A-Z)' },
  { value: '-name', children: 'Alphabetical (Z-A)' },
  { value: 'created_at', children: 'Created (Newest First)' },
  { value: '-created_at', children: 'Created (Oldest First)' },
];

const makeFilterColumns: ComponentProps<typeof DataView.Root<ModelEntity>>['makeColumns'] = ({
  accessor,
}) => [
  accessor('created_at', {
    id: 'created_at',
    header: 'Created',
    enableSorting: false,
    meta: { filter: dateTimeFilter('Created At') },
  }),
  accessor('updated_at', {
    id: 'updated_at',
    header: 'Updated',
    enableSorting: false,
    meta: { filter: dateTimeFilter('Updated At') },
  }),
];

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const fixedHeightDecorator = (Story: FC) => (
  <div className="h-[700px]">
    <Story />
  </div>
);

const meta: Meta = {
  title: 'Studio Common/VirtualizedCardGrid',
  parameters: { layout: 'padded' },
};

export default meta;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/**
 * Standalone VirtualizedCardGrid with a simple scroll container.
 * Demonstrates basic virtualization without StudioDataView.
 */
export const Standalone: StoryObj = {
  decorators: [fixedHeightDecorator],
  name: 'Standalone (Simple)',
  render: function StandaloneStory() {
    const scrollRef = useRef<HTMLDivElement>(null);
    const models = generateModels(100);

    return (
      <div className="relative h-full">
        <div ref={scrollRef} className="absolute inset-0 overflow-auto p-6">
          <VirtualizedCardGrid
            items={models}
            renderCard={(model) => <BaseModelCard model={model} isChatAvailable />}
            getItemKey={(model) => `${model.workspace}/${model.name}`}
            scrollContainerRef={scrollRef}
          />
        </div>
      </div>
    );
  },
};

/**
 * Simulates infinite scroll by loading 50 models at a time with a 500ms delay.
 * Watch the spinner appear at the bottom and new cards load in.
 */
export const InfiniteScroll: StoryObj = {
  decorators: [fixedHeightDecorator],
  name: 'Infinite Scroll',
  render: function InfiniteScrollStory() {
    const scrollRef = useRef<HTMLDivElement>(null);
    const PAGE_SIZE = 50;
    const [loadedCount, setLoadedCount] = useState(PAGE_SIZE);
    const [isLoading, setIsLoading] = useState(false);

    const items = ALL_MODELS.slice(0, loadedCount);
    const hasMore = loadedCount < ALL_MODELS.length;

    const onLoadMore = useCallback(async () => {
      setIsLoading(true);
      await new Promise((r) => setTimeout(r, 500));
      setLoadedCount((prev) => Math.min(prev + PAGE_SIZE, ALL_MODELS.length));
      setIsLoading(false);
    }, []);

    return (
      <Stack className="h-full" gap="density-md">
        <Flex justify="between" align="center" className="shrink-0 px-2">
          <Text kind="body/regular/md" className="text-secondary">
            Showing {items.length} of {ALL_MODELS.length} models
            {isLoading && ' (loading...)'}
          </Text>
        </Flex>
        <div className="relative flex-1 min-h-0">
          <div ref={scrollRef} className="absolute inset-0 overflow-auto p-6">
            <VirtualizedCardGrid
              items={items}
              renderCard={(model) => <BaseModelCard model={model} isChatAvailable />}
              getItemKey={(model) => `${model.workspace}/${model.name}`}
              scrollContainerRef={scrollRef}
              hasMore={hasMore}
              onLoadMore={onLoadMore}
            />
          </div>
        </div>
      </Stack>
    );
  },
};

/**
 * Full DataView integration matching the WorkspaceBaseModelsRoute pattern.
 * Includes toolbar, search, filters, sort dropdown, and virtualized card grid.
 */
export const DataViewIntegration: StoryObj = {
  name: 'DataView Integration (Full Page)',
  parameters: { layout: 'fullscreen' },
  render: function DataViewIntegrationStory() {
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const PAGE_SIZE = 50;
    const [loadedCount, setLoadedCount] = useState(PAGE_SIZE);

    const dataViewState = useStudioDataViewState({
      defaultSort: [{ id: 'name', desc: false }],
    });

    const items = ALL_MODELS.slice(0, loadedCount);
    const hasMore = loadedCount < ALL_MODELS.length;

    const onLoadMore = useCallback(async () => {
      await new Promise((r) => setTimeout(r, 500));
      setLoadedCount((prev) => Math.min(prev + PAGE_SIZE, ALL_MODELS.length));
    }, []);

    const sortSelectValue = dataViewState.sorting.state[0]
      ? dataViewState.sorting.state[0].desc
        ? `-${dataViewState.sorting.state[0].id}`
        : dataViewState.sorting.state[0].id
      : 'name';

    return (
      <Stack className="h-dvh" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0 shrink-0"
          slotHeading="Base Models"
          slotDescription={`${items.length} of ${ALL_MODELS.length} models loaded`}
        />
        <StudioDataView<ModelEntity>
          dataViewState={dataViewState}
          makeColumns={makeFilterColumns}
          searchField="name"
          scrollContainerRef={scrollContainerRef}
          toolbarSlotEnd={
            <Select
              className="shrink-0 w-fit"
              items={SORT_OPTIONS}
              value={sortSelectValue}
              onValueChange={(value) => {
                const desc = value.startsWith('-');
                dataViewState.sorting.set([{ id: desc ? value.slice(1) : value, desc }]);
              }}
            />
          }
          attributes={{
            DataViewRoot: {
              className: 'flex-1 min-h-0',
              data: items,
              totalCount: items.length,
            },
            DataViewSearchBar: { placeholder: 'Search Models...' },
          }}
        >
          <DataView.CustomContent<ModelEntity>
            renderLoadingState={() => (
              <Flex align="center" justify="center" className="h-full">
                <Spinner size="large" description="Loading base models..." />
              </Flex>
            )}
            renderEmptyState={() => (
              <Flex align="center" justify="center" className="h-full">
                <Text className="text-secondary">No base models match your search or filters.</Text>
              </Flex>
            )}
          >
            {({ rows }) => (
              <VirtualizedCardGrid
                items={rows.map((r) => r.original)}
                renderCard={(model) => (
                  <BaseModelCard
                    model={model}
                    isChatAvailable
                    onClick={() => alert(`Clicked: ${model.name}`)}
                  />
                )}
                getItemKey={(model) => `${model.workspace}/${model.name}`}
                scrollContainerRef={scrollContainerRef}
                hasMore={hasMore}
                onLoadMore={onLoadMore}
              />
            )}
          </DataView.CustomContent>
        </StudioDataView>
      </Stack>
    );
  },
};

/**
 * Small number of items to verify the grid works without virtualization kicking in.
 */
export const FewItems: StoryObj = {
  decorators: [fixedHeightDecorator],
  name: 'Few Items (No Scroll)',
  render: function FewItemsStory() {
    const scrollRef = useRef<HTMLDivElement>(null);
    const models = generateModels(5);

    return (
      <div className="relative h-full">
        <div ref={scrollRef} className="absolute inset-0 overflow-auto p-6">
          <VirtualizedCardGrid
            items={models}
            renderCard={(model) => <BaseModelCard model={model} isChatAvailable />}
            getItemKey={(model) => `${model.workspace}/${model.name}`}
            scrollContainerRef={scrollRef}
          />
        </div>
      </div>
    );
  },
};

/**
 * 250 models loaded at once to stress-test virtualization.
 * Open DevTools Elements tab to verify only ~15-20 card rows exist in the DOM.
 */
export const StressTest: StoryObj = {
  decorators: [fixedHeightDecorator],
  name: 'Stress Test (250 Items)',
  render: function StressTestStory() {
    const scrollRef = useRef<HTMLDivElement>(null);

    return (
      <Stack className="h-full" gap="density-md">
        <Text kind="body/regular/md" className="text-secondary shrink-0 px-2">
          250 models rendered with virtualization. Inspect the DOM to verify only visible rows
          exist.
        </Text>
        <div className="relative flex-1 min-h-0">
          <div ref={scrollRef} className="absolute inset-0 overflow-auto p-6">
            <VirtualizedCardGrid
              items={ALL_MODELS}
              renderCard={(model) => <BaseModelCard model={model} isChatAvailable />}
              getItemKey={(model) => `${model.workspace}/${model.name}`}
              scrollContainerRef={scrollRef}
            />
          </div>
        </div>
      </Stack>
    );
  },
};

/**
 * Fixed 2-column grid to test custom gridClassName prop.
 */
export const CustomColumns: StoryObj = {
  decorators: [fixedHeightDecorator],
  name: 'Custom Grid (2 Columns)',
  render: function CustomColumnsStory() {
    const scrollRef = useRef<HTMLDivElement>(null);
    const models = generateModels(40);

    return (
      <div className="relative h-full">
        <div ref={scrollRef} className="absolute inset-0 overflow-auto p-6">
          <VirtualizedCardGrid
            items={models}
            renderCard={(model) => <BaseModelCard model={model} isChatAvailable />}
            getItemKey={(model) => `${model.workspace}/${model.name}`}
            scrollContainerRef={scrollRef}
            gridClassName="grid grid-cols-2 gap-6"
          />
        </div>
      </div>
    );
  },
};

/**
 * Renders simple placeholder cards to isolate virtualizer behavior
 * from BaseModelCard rendering complexity.
 */
export const SimplePlaceholderCards: StoryObj = {
  decorators: [fixedHeightDecorator],
  name: 'Simple Cards (Debug)',
  render: function SimplePlaceholderStory() {
    const scrollRef = useRef<HTMLDivElement>(null);
    const items = Array.from({ length: 200 }, (_, i) => ({
      id: `item-${i}`,
      label: `Card ${i + 1}`,
    }));

    return (
      <div className="relative h-full">
        <div ref={scrollRef} className="absolute inset-0 overflow-auto p-6">
          <VirtualizedCardGrid
            items={items}
            renderCard={(item) => (
              <div className="border border-base rounded-lg p-4 bg-surface-raised h-[200px] flex items-center justify-center">
                <Text kind="title/sm">{item.label}</Text>
              </div>
            )}
            getItemKey={(item) => item.id}
            scrollContainerRef={scrollRef}
            estimateRowHeight={224}
          />
        </div>
      </div>
    );
  },
};
