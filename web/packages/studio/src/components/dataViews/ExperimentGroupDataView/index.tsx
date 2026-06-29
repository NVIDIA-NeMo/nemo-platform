// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import {
  Root as DataViewRoot,
  EditColumnsMenu,
} from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { snakeCaseToTitleCase } from '@nemo/common/src/utils/formatters';
import { useGetExperimentGroup } from '@nemo/sdk/generated/platform/api';
import type { ExperimentFilter } from '@nemo/sdk/generated/platform/schema';
import { Button, Text, Tooltip } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/dataViews/ExperimentGroupDataView/Empty';
import { MeanValueTooltipCell } from '@studio/components/dataViews/ExperimentGroupDataView/MeanValueTooltipCell';
import {
  type ExperimentRow,
  type ListExperimentsSortParam,
  useExperimentGroupExperiments,
} from '@studio/components/dataViews/ExperimentGroupDataView/useExperimentGroupExperiments';
import { useSortErrorRecovery } from '@studio/components/dataViews/ExperimentGroupDataView/useSortErrorRecovery';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentDetailRoute } from '@studio/routes/utils';
import { tooltipClassName } from '@studio/styles/common';
import { Columns3, Pin } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

export type { ExperimentRow };

const DEFAULT_SORT: ListExperimentsSortParam = '-created_at';

// Maps sortable static column ids to their API sort fields.
const STATIC_SORT_FIELD_MAP: Readonly<Record<string, string>> = {
  name: 'name',
  created_at: 'created_at',
  cost_usd: 'cost_usd.mean',
  latency_ms: 'latency_ms.mean',
  run_count: 'run_count',
};

const getExperimentSortParam = (
  sortingState: { id: string; desc: boolean }[]
): ListExperimentsSortParam => {
  const [first] = sortingState;
  if (!first) return DEFAULT_SORT;
  let field = STATIC_SORT_FIELD_MAP[first.id];
  if (!field) {
    // Evaluator columns use id `evaluator-<name>` so the API field can be derived without
    // a separate lookup into evaluatorNames (which would create a circular dependency).
    const evaluatorMatch = first.id.match(/^evaluator-(.+)$/);
    if (evaluatorMatch) field = `evaluators.${evaluatorMatch[1]}.mean`;
  }
  if (!field) return DEFAULT_SORT;
  return `${first.desc ? '-' : ''}${field}`;
};

interface ExperimentGroupDataViewProps {
  experimentGroupName: string;
}

/**
 * Formats an evaluator's mean score for display. Scores in the normalized 0–1 range read
 * best as percentages; values outside that range are on a different scale (e.g. a 1–5 or
 * 1–10 rubric), so they're shown as a raw number rather than a misleading percentage.
 */
const formatEvaluatorScore = (mean: number | null | undefined): string => {
  if (mean == null || !Number.isFinite(mean)) return '-';
  return mean >= 0 && mean <= 1 ? `${(mean * 100).toFixed(1)}%` : mean.toFixed(3);
};

/** Lists the experiments that belong to a single experiment group. */
export const ExperimentGroupDataView: FC<ExperimentGroupDataViewProps> = ({
  experimentGroupName,
}) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const toast = useToast();
  const {
    data: group,
    isLoading: isGroupLoading,
    error: groupError,
  } = useGetExperimentGroup(workspace, experimentGroupName);
  const experimentGroupId = group?.id ?? '';

  const dataViewState = useStudioDataViewState<ExperimentFilter>({
    defaultSort: { id: 'created_at', desc: true },
    // created_by isn't returned by the API and updated_at isn't shown; both are filter-only.
    columnVisibility: { created_by: false, updated_at: false },
    // Keep the pin toggle reachable while horizontally scrolling this wide table.
    columnPinning: { left: ['pin'] },
  });

  const page = dataViewState.pagination.state.pageIndex + 1;
  const pageSize = dataViewState.pagination.state.pageSize;
  const sortParam = getExperimentSortParam(dataViewState.sorting.state);

  const {
    rows: orderedData,
    togglePin,
    totalCount,
    error,
    isLoading,
    isSuccess,
  } = useExperimentGroupExperiments({
    workspace,
    experimentGroupId,
    filter: dataViewState.apiFilter.filter,
    search: dataViewState.debouncedSearchBar,
    page,
    pageSize,
    sort: sortParam,
  });

  // A metric sort (cost, latency, evaluator score) can fail with 413/503/400. Recover by toasting
  // and reverting the sort indicator to the last good sort instead of replacing the table with an
  // error; `isRecoverableSortError` lets us skip the page-level error for that case.
  const isRecoverableSortError = useSortErrorRecovery({
    error,
    isSuccess,
    sortingState: dataViewState.sorting.state,
    setSorting: dataViewState.sorting.set,
    onError: toast.error,
  });

  // One score column per evaluator: the union of evaluator names across the loaded rows,
  // sorted for a deterministic column order across renders and page changes.
  const evaluatorNames = useMemo(
    () => [...new Set(orderedData.flatMap((e) => Object.keys(e.aggregate_scores ?? {})))].sort(),
    [orderedData]
  );

  // One column per metadata key: keys are lowercased so case variants (e.g. "status"
  // and "Status") collapse into one column rather than producing duplicate headers.
  const metadataKeys = useMemo(
    () =>
      [
        ...new Set(
          orderedData.flatMap((e) => Object.keys(e.metadata ?? {}).map((k) => k.toLowerCase()))
        ),
      ].sort(),
    [orderedData]
  );

  const makeColumns = useCallback<
    ComponentProps<typeof DataViewRoot<ExperimentRow>>['makeColumns']
  >(
    ({ accessor, display }) => [
      display({
        id: 'pin',
        header: () => <span className="sr-only">Pinned</span>,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        size: 48,
        minSize: 48,
        maxSize: 48,
        meta: { alignment: 'center', _isPrebuiltColumn: true, _isSizeInitialized: true },
        cell: ({ row }) => {
          const { pinned_at } = row.original;
          const isPinned = pinned_at != null;
          return (
            <Button
              kind="tertiary"
              color="neutral"
              size="small"
              aria-label={isPinned ? 'Unpin experiment' : 'Pin experiment'}
              aria-pressed={isPinned}
              onClick={() => togglePin(row.original)}
            >
              <Pin
                className={isPinned ? 'text-brand' : 'text-secondary'}
                {...(isPinned ? { fill: 'currentColor' } : {})}
              />
            </Button>
          );
        },
      }),
      accessor('name', {
        header: 'Name',
        enableSorting: true,
        enableHiding: false,
        meta: { title: false },
        size: 300,
        cell: ({ row }) => {
          const { name, summary } = row.original;
          if (!summary) return <Text>{name}</Text>;
          return (
            <Tooltip
              slotContent={
                <div className="flex flex-col gap-1">
                  <Text kind="label/regular/sm" className="text-secondary">
                    Summary
                  </Text>
                  <Text kind="body/regular/sm">{summary}</Text>
                </div>
              }
              className={tooltipClassName}
              side="bottom"
            >
              <Text className="cursor-default border-b border-dotted border-brand">{name}</Text>
            </Tooltip>
          );
        },
      }),
      accessor((original) => original.agent_names?.join(', '), {
        id: 'agent_names',
        header: 'Agent Names',
        enableSorting: false,
        cell: ({ getValue }) => <Text>{getValue<string>() || '-'}</Text>,
      }),
      accessor((original) => original.agent_versions?.join(', '), {
        id: 'agent_versions',
        header: 'Agent Versions',
        enableSorting: false,
        cell: ({ getValue }) => <Text>{getValue<string>() || '-'}</Text>,
      }),
      accessor('dataset_name', {
        header: 'Dataset Name',
        enableSorting: false,
        meta: {
          filter: { type: 'text', label: 'Dataset Name', placeholder: 'Filter by Dataset Name' },
        },
        cell: ({ row }) => <Text>{row.original.dataset_name || '-'}</Text>,
      }),
      accessor('dataset_version', {
        header: 'Dataset Version',
        enableSorting: false,
        meta: {
          filter: {
            type: 'text',
            label: 'Dataset Version',
            placeholder: 'Filter by Dataset Version',
          },
        },
        cell: ({ row }) => <Text>{row.original.dataset_version || '-'}</Text>,
      }),
      accessor((original) => original.model_names?.join(', '), {
        id: 'model_names',
        header: 'Models',
        enableSorting: false,
        cell: ({ getValue }) => <Text>{getValue<string>() || '-'}</Text>,
      }),
      ...metadataKeys.map((key) =>
        accessor(
          (original) => {
            const meta = original.metadata ?? {};
            // Match the first key that lowercases to this column's key.
            const match = Object.keys(meta).find((k) => k.toLowerCase() === key);
            return match ? meta[match] : undefined;
          },
          {
            id: `metadata-${key}`,
            header: snakeCaseToTitleCase(key),
            enableSorting: false,
            cell: ({ getValue }) => {
              const raw = getValue<unknown>();
              if (raw == null) return <Text>-</Text>;
              const str = typeof raw === 'object' ? JSON.stringify(raw) : String(raw);
              if (str.length <= 50) return <Text>{str}</Text>;
              return (
                <Tooltip
                  slotContent={<Text kind="body/regular/sm">{str}</Text>}
                  className={tooltipClassName}
                  side="bottom"
                >
                  <Text className="cursor-default">{str.slice(0, 50)}…</Text>
                </Tooltip>
              );
            },
          }
        )
      ),
      ...evaluatorNames.map((name) => {
        const title = snakeCaseToTitleCase(name);
        return accessor((original) => original.aggregate_scores?.[name]?.mean, {
          id: `evaluator-${name}`,
          header: `Avg ${title}`,
          enableSorting: true,
          meta: { title: false },
          size: 140,
          cell: ({ row }) => {
            const score = row.original.aggregate_scores?.[name];
            return (
              <MeanValueTooltipCell
                label={title}
                runNoun="scored run"
                count={score?.count}
                runCount={row.original.run_count}
              >
                {formatEvaluatorScore(score?.mean)}
              </MeanValueTooltipCell>
            );
          },
        });
      }),
      accessor((original) => original.cost_usd?.mean, {
        id: 'cost_usd',
        header: 'Avg Cost',
        enableSorting: true,
        meta: { title: false },
        cell: ({ row }) => {
          const { cost_usd, run_count } = row.original;
          return (
            <MeanValueTooltipCell
              label="cost"
              runNoun="run"
              count={cost_usd?.count}
              runCount={run_count}
            >
              {cost_usd?.mean != null ? `$${cost_usd.mean.toFixed(3)}` : '-'}
            </MeanValueTooltipCell>
          );
        },
      }),
      accessor((original) => original.latency_ms?.mean, {
        id: 'latency_ms',
        header: 'Avg Latency',
        meta: { title: false },
        enableSorting: true,
        cell: ({ row }) => {
          const { latency_ms, run_count } = row.original;
          return (
            <MeanValueTooltipCell
              label="latency"
              runNoun="run"
              count={latency_ms?.count}
              runCount={run_count}
            >
              {latency_ms?.mean != null ? `${Math.round(latency_ms.mean)} ms` : '-'}
            </MeanValueTooltipCell>
          );
        },
      }),
      accessor((original) => original.run_count, {
        id: 'run_count',
        header: 'Run Count',
        enableSorting: true,
        cell: ({ row }) => <Text>{String(row.original.run_count ?? 0)}</Text>,
      }),
      accessor('created_at', {
        header: 'Created',
        size: 200,
        enableSorting: true,
        meta: { filter: dateTimeFilter('Created At') },
        cell: ({ row }) =>
          row.original.created_at ? (
            <RelativeTime datetime={row.original.created_at} />
          ) : (
            <Text>-</Text>
          ),
      }),
      // Filter-only columns (hidden via columnVisibility above).
      accessor(() => '', {
        id: 'created_by',
        header: 'Created By',
        enableSorting: false,
        enableHiding: false,
        meta: {
          filter: { type: 'text', label: 'Created By', placeholder: 'Filter by Created By' },
        },
      }),
    ],
    [evaluatorNames, togglePin, metadataKeys]
  );

  if (groupError) {
    return <ErrorMessage message="Failed to load experiment group." />;
  }

  // A recoverable sort error is handled by useSortErrorRecovery (toast + revert), and the table keeps
  // showing the last good page — so don't replace it with the full-page error for that case.
  if (error && !isRecoverableSortError) {
    return <ErrorMessage message="Failed to load experiments." />;
  }

  return (
    <StudioDataView
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      searchField="name"
      onRowClick={(row) =>
        navigate(getExperimentDetailRoute(workspace, experimentGroupName, row.name))
      }
      toolbarSlotEnd={
        <EditColumnsMenu
          kind="secondary"
          showChevron={false}
          // EditColumnsMenu exposes no width control for its dropdown, so this zero-height
          // spacer sets a min width on the menu (which sizes to its widest child).
          slotContent={<div aria-hidden className="h-0 w-[230px]" />}
        >
          <>
            <Columns3 />
            <span className="hide-mobile">Columns</span>
          </>
        </EditColumnsMenu>
      }
      attributes={{
        DataViewRoot: {
          data: orderedData,
          totalCount,
          requestStatus: isGroupLoading || isLoading ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: ({ hasFiltersApplied, hasSearchApplied }) =>
            hasFiltersApplied || hasSearchApplied ? null : (
              <Empty experimentGroupName={experimentGroupName} />
            ),
        },
      }}
    />
  );
};
