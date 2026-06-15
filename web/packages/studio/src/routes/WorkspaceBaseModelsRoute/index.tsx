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

import {
  useBaseModels,
  type ModelEntityFilterInput,
} from '@nemo/common/src/api/entity-store/useBaseModels';
import { usePromptTunableBaseModelIds } from '@nemo/common/src/api/entity-store/usePromptTunableBaseModelIds';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getModelEntityChatStatus } from '@nemo/common/src/utils/models';
import { getSortParam } from '@nemo/common/src/utils/query';
import { useModelsGetModel } from '@nemo/sdk/generated/platform/api';
import type { ModelEntity, ModelEntitySortField } from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  Checkbox,
  Flex,
  PageHeader,
  Select,
  Spinner,
  Stack,
  Text,
  Tooltip,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { BaseModelCard } from '@studio/components/BaseModelCard';
import { CustomizeModelButton } from '@studio/components/dataViews/CustomModelsDataView/CustomizeModelButton';
import { ModelPanel, ModelPanelTab } from '@studio/components/sidePanels/ModelPanels/ModelPanel';
import { VirtualizedCardGrid } from '@studio/components/VirtualizedCardGrid';
import { CUSTOMIZER_ENABLED, EVALUATOR_ENABLED } from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getEvaluationResultsRoute, getWorkspaceBaseModelsRoute } from '@studio/routes/utils';
import { tooltipClassName } from '@studio/styles/common';
import { useEffect, useMemo, useRef, useState, type ComponentProps, type FC } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

const SORT_OPTIONS = [
  { value: 'name', children: 'Alphabetical (A-Z)' },
  { value: '-name', children: 'Alphabetical (Z-A)' },
  { value: 'created_at', children: 'Created (Newest First)' },
  { value: '-created_at', children: 'Created (Oldest First)' },
];

const TAB_SEARCH_PARAM = 'tab';

const CUSTOMIZABLE_FILTER_ID = 'customizable';
const FINE_TUNABLE_KEY = 'fine_tunable';
const PROMPT_TUNABLE_KEY = 'prompt_tunable';

type CustomizableFilterState = Partial<
  Record<typeof FINE_TUNABLE_KEY | typeof PROMPT_TUNABLE_KEY, true>
>;

/**
 * Column definitions used solely for filter metadata. The columns are never rendered as a table;
 * they only provide `meta.filter` config so that DataView's ColumnFilterPanel and
 * StudioAppliedFilters components can render and manage the filter UI.
 */
const makeFilterColumns: ComponentProps<typeof DataView.Root<ModelEntity>>['makeColumns'] = ({
  accessor,
}) => [
  // Customizable filtering depends on Customizer capabilities, so hide both the
  // column filter and toolbar checkbox while Customizer is launch-disabled.
  ...(CUSTOMIZER_ENABLED
    ? [
        accessor(() => '', {
          id: CUSTOMIZABLE_FILTER_ID,
          header: 'Customizable',
          enableSorting: false,
          meta: {
            filter: {
              type: 'multi-select',
              label: 'Customizable',
              options: [
                { value: FINE_TUNABLE_KEY, label: 'Fine-tunable' },
                { value: PROMPT_TUNABLE_KEY, label: 'Prompt tunable' },
              ],
            },
          },
        }),
      ]
    : []),
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

export const WorkspaceBaseModelsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { modelName: modelNameParam } = useParams<{ modelName?: string }>();
  const tabFromUrl = (searchParams.get(TAB_SEARCH_PARAM) ?? 'model-details') as ModelPanelTab;

  useBreadcrumbs({
    items: [{ slotLabel: 'Base Models' }],
  });

  const dataViewState = useStudioDataViewState<
    Partial<ModelEntityFilterInput> & { [CUSTOMIZABLE_FILTER_ID]?: CustomizableFilterState }
  >({
    defaultSort: { id: 'name', desc: false },
  });

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [selectedModel, setSelectedModel] = useState<ModelEntity | null>(null);

  const modelNameFromPath = decodeURIComponent(modelNameParam ?? '');

  const nameSearch = dataViewState.apiFilter.searchText;
  const allColumnFilters = dataViewState.apiFilter.filter;
  const customizableFilter = CUSTOMIZER_ENABLED
    ? allColumnFilters?.[CUSTOMIZABLE_FILTER_ID]
    : undefined;

  // Strip the synthetic `customizable` filter from the API filter — the backend doesn't know about it.
  const apiColumnFilters = useMemo(() => {
    if (!allColumnFilters) return undefined;
    const rest = { ...allColumnFilters };
    delete rest[CUSTOMIZABLE_FILTER_ID];
    return Object.keys(rest).length > 0 ? (rest as Partial<ModelEntityFilterInput>) : undefined;
  }, [allColumnFilters]);

  const customizableFilterActive = !!(
    customizableFilter && Object.keys(customizableFilter).length > 0
  );

  // Only blame the Customizable filter for an empty result when it's the *only* active filter —
  // otherwise a name search or date filter could be the real cause and we'd misreport it.
  const onlyCustomizableFilterActive = customizableFilterActive && !nameSearch && !apiColumnFilters;

  const hasActiveFilters = !!nameSearch || !!apiColumnFilters || customizableFilterActive;

  const filter = useMemo<ModelEntityFilterInput | undefined>(() => {
    if (!nameSearch && !apiColumnFilters) return undefined;
    return {
      ...apiColumnFilters,
      ...(nameSearch ? { name: { $like: nameSearch } } : {}),
    };
  }, [apiColumnFilters, nameSearch]);

  const sort = getSortParam(dataViewState.sorting.state) as ModelEntitySortField;

  const {
    models,
    isLoading,
    isError,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
    refetch,
  } = useBaseModels({
    workspace,
    filter,
    sort,
  });

  const { promptTunableIds } = usePromptTunableBaseModelIds({ workspace });

  const visibleModels = useMemo(() => {
    const wantFineTunable = !!customizableFilter?.[FINE_TUNABLE_KEY];
    const wantPromptTunable = !!customizableFilter?.[PROMPT_TUNABLE_KEY];
    if (!wantFineTunable && !wantPromptTunable) return models;
    return models.filter((model) => {
      const isFineTuneable = Boolean(model.fileset);
      const isChatAvailable = getModelEntityChatStatus(model) === 'enabled';
      const canPromptTune = promptTunableIds.has(model.id);
      if (wantFineTunable && isFineTuneable) return true;
      if (wantPromptTunable && canPromptTune && isChatAvailable) return true;
      return false;
    });
  }, [models, customizableFilter, promptTunableIds]);

  const liveCustomizableFilter = CUSTOMIZER_ENABLED
    ? (dataViewState.columnFiltering.state.find((f) => f.id === CUSTOMIZABLE_FILTER_ID)?.value as
        | CustomizableFilterState
        | undefined)
    : undefined;
  const customizableChecked =
    !!liveCustomizableFilter?.[FINE_TUNABLE_KEY] || !!liveCustomizableFilter?.[PROMPT_TUNABLE_KEY];

  const handleCustomizableToggle = (checked: boolean) => {
    dataViewState.columnFiltering.set((prev) => {
      const others = prev.filter((f) => f.id !== CUSTOMIZABLE_FILTER_ID);
      if (!checked) return others;
      return [
        ...others,
        {
          id: CUSTOMIZABLE_FILTER_ID,
          value: { [FINE_TUNABLE_KEY]: true, [PROMPT_TUNABLE_KEY]: true },
        },
      ];
    });
  };

  const isSweepingForCustomizable =
    customizableChecked && visibleModels.length === 0 && hasNextPage && !isFetchNextPageError;

  // In the rare case where the user is filtering for customizable models and there are no visible models on the first page,
  // fetch the next page here because the table won't render the virutalized cards, preventing a refetch from happening.
  useEffect(() => {
    if (isSweepingForCustomizable && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [fetchNextPage, isSweepingForCustomizable, isFetchingNextPage]);

  const modelInList = useMemo(
    () => !!modelNameFromPath && models.some((m) => m.name === modelNameFromPath),
    [modelNameFromPath, models]
  );
  const { data: modelFromApi, isLoading: isModelFromApiLoading } = useModelsGetModel(
    workspace,
    modelNameFromPath ?? '',
    undefined,
    {
      query: {
        enabled: !!workspace && !!modelNameFromPath && !modelInList,
      },
    }
  );

  const resolvedModelFromPath = useMemo(() => {
    if (!modelNameFromPath) return null;
    const fromList = models.find((m) => m.name === modelNameFromPath);
    if (fromList) return fromList;
    if (modelFromApi?.name === modelNameFromPath) return modelFromApi;
    return null;
  }, [modelNameFromPath, models, modelFromApi]);

  useEffect(() => {
    if (modelNameFromPath && resolvedModelFromPath) {
      setSelectedModel(resolvedModelFromPath);
    }
  }, [modelNameFromPath, resolvedModelFromPath]);

  const handleOpenPanel = (model: ModelEntity) => {
    setSelectedModel(model);
    navigate(getWorkspaceBaseModelsRoute(workspace, { model: model.name, searchParams }), {
      replace: true,
    });
  };

  const handleClosePanel = () => {
    const listSearchParams = new URLSearchParams(searchParams);
    listSearchParams.delete(TAB_SEARCH_PARAM);

    setSelectedModel(null);
    navigate(getWorkspaceBaseModelsRoute(workspace, { searchParams: listSearchParams }), {
      replace: true,
    });
  };

  /** Base models can only be deleted when no `model_providers` entries reference them. */
  const allowModelDelete = !!selectedModel && !(selectedModel.model_providers?.length ?? 0);

  const sortSelectValue = dataViewState.sorting.state[0]
    ? dataViewState.sorting.state[0].desc
      ? `-${dataViewState.sorting.state[0].id}`
      : dataViewState.sorting.state[0].id
    : 'name';

  return (
    <AccessibleTitle title="Base Models">
      <ModelPanel
        allowModelDelete={allowModelDelete}
        onModelDeleted={() => {
          void refetch();
        }}
        open={
          !!selectedModel ||
          !!(modelNameFromPath && (!!resolvedModelFromPath || isModelFromApiLoading))
        }
        loading={!!modelNameFromPath && !resolvedModelFromPath && isModelFromApiLoading}
        overviewProps={{
          slotActions: (
            <Flex gap="density-md" align="center">
              {CUSTOMIZER_ENABLED && selectedModel && (
                <CustomizeModelButton model={selectedModel} workspace={workspace} />
              )}
              {EVALUATOR_ENABLED && (
                <Button
                  kind="secondary"
                  size="small"
                  onClick={() => navigate(getEvaluationResultsRoute(workspace))}
                  className="flex-1"
                >
                  Evaluate this Model
                </Button>
              )}
            </Flex>
          ),
        }}
        model={selectedModel ?? undefined}
        showCustomizationDetails={CUSTOMIZER_ENABLED}
        defaultTab={tabFromUrl}
        onTabChange={(tab) =>
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev);
              next.set(TAB_SEARCH_PARAM, tab);
              return next;
            },
            { replace: true }
          )
        }
        onOpenChange={(open) => !open && handleClosePanel()}
      />
      <Stack className="h-full min-h-0" gap="density-2xl" padding="density-2xl">
        <PageHeader className="p-0 shrink-0" slotHeading="Base Models" />
        <StudioDataView<ModelEntity>
          dataViewState={dataViewState}
          makeColumns={makeFilterColumns}
          searchField="name"
          scrollContainerRef={scrollContainerRef}
          toolbarSlotEnd={
            <Flex gap="density-md" align="center">
              {CUSTOMIZER_ENABLED && (
                <Tooltip
                  slotContent={
                    <div className={tooltipClassName}>
                      <Text>
                        Show only models that can be fine-tuned or prompt-tuned. Inference-only
                        models (e.g. from custom providers) are hidden.
                      </Text>
                    </div>
                  }
                  side="bottom"
                >
                  <Flex
                    align="center"
                    className="h-10 px-density-md rounded-md border border-base bg-surface-raised"
                  >
                    <Checkbox
                      attributes={{
                        CheckboxInput: { id: 'base-models-filter-customizable' },
                        Label: { htmlFor: 'base-models-filter-customizable' },
                      }}
                      checked={customizableChecked}
                      slotLabel="Customizable"
                      onCheckedChange={(checked) => handleCustomizableToggle(!!checked)}
                    />
                  </Flex>
                </Tooltip>
              )}
              <Select
                className="w-fit"
                items={SORT_OPTIONS}
                value={sortSelectValue}
                onValueChange={(value) => {
                  const desc = value.startsWith('-');
                  dataViewState.sorting.set([{ id: desc ? value.slice(1) : value, desc }]);
                }}
              />
            </Flex>
          }
          attributes={{
            DataViewRoot: {
              data: visibleModels,
              totalCount: visibleModels.length,
              requestStatus:
                isLoading || isSweepingForCustomizable
                  ? 'loading'
                  : isError || isFetchNextPageError
                    ? 'error'
                    : 'success',
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
              <TableEmptyState
                header="No Base Models Available"
                emptyMessage={
                  onlyCustomizableFilterActive
                    ? "No customizable models in this workspace. Inference-only models (e.g. from custom providers) can't be fine-tuned or prompt-tuned in Studio."
                    : hasActiveFilters
                      ? 'No base models match your search or filters.'
                      : 'No base models have been deployed yet.'
                }
              />
            )}
            renderErrorState={() => (
              <Stack align="center" justify="center" gap="density-md" className="h-full">
                <TableEmptyState
                  header="Failed to Load Base Models"
                  emptyMessage="An error occurred while loading base models."
                />
                <Button kind="secondary" onClick={() => refetch()}>
                  Retry
                </Button>
              </Stack>
            )}
          >
            {({ rows }) => (
              <VirtualizedCardGrid
                items={rows.map((r) => r.original)}
                renderCard={(model) => (
                  <BaseModelCard
                    model={model}
                    isChatAvailable={getModelEntityChatStatus(model) === 'enabled'}
                    canPromptTune={promptTunableIds.has(model.id)}
                    showCustomizationBadges={CUSTOMIZER_ENABLED}
                    onClick={() => handleOpenPanel(model)}
                  />
                )}
                getItemKey={(model) => `${model.workspace}/${model.name}`}
                scrollContainerRef={scrollContainerRef}
                hasMore={hasNextPage}
                onLoadMore={fetchNextPage}
              />
            )}
          </DataView.CustomContent>
        </StudioDataView>
      </Stack>
    </AccessibleTitle>
  );
};
