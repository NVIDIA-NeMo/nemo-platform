// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { numberRangeFilter } from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter/util';
import {
  Root as DataViewRoot,
  EditColumnsMenu,
} from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { formatDurationMs } from '@nemo/common/src/utils/date';
import { snakeCaseToTitleCase } from '@nemo/common/src/utils/formatters';
import type {
  EvaluationFilter,
  ExperimentGroupResponse,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Text, Tooltip } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/dataViews/ExperimentGroupDataView/Empty';
import { MeanValueTooltipCell } from '@studio/components/dataViews/ExperimentGroupDataView/MeanValueTooltipCell';
import {
  type EvaluationRow,
  type ListEvaluationsSortParam,
  useExperimentGroupEvaluations,
} from '@studio/components/dataViews/ExperimentGroupDataView/useExperimentGroupEvaluations';
import { useSortErrorRecovery } from '@studio/components/dataViews/ExperimentGroupDataView/useSortErrorRecovery';
import { deriveEvaluatorNames } from '@studio/components/dataViews/ExperimentGroupDataView/util';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getEvaluationDetailRoute } from '@studio/routes/utils';
import { tooltipClassName } from '@studio/styles/common';
import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { Columns3, Pin } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

export type { EvaluationRow };

const DEFAULT_SORT: ListEvaluationsSortParam = '-created_at';

// Maps sortable static column ids to their API sort fields.
const STATIC_SORT_FIELD_MAP: Readonly<Record<string, string>> = {
  name: 'name',
  created_at: 'created_at',
  cost_usd: 'cost_usd.mean',
  latency_ms: 'latency_ms.mean',
  test_case_count: 'test_case_count',
};

// Resolves a group's default_sort (a `sort`-param string like `-cost_usd.mean` or `-created_at`) to
// the table's initial sort so the matching column header shows the sort on load. Entity columns map
// by exact id; metric columns match on the family (any stat) since the column always sorts on `.mean`.
// Maps one API sort field to its table column id: entity columns by exact id; metric columns by
// family (any stat) since the column always sorts on `.mean`.
const sortFieldToColumnId = (field: string): string | undefined => {
  if (field === 'name' || field === 'created_at' || field === 'test_case_count') return field;
  if (field.startsWith('cost_usd.')) return 'cost_usd';
  if (field.startsWith('latency_ms.')) return 'latency_ms';
  const evaluatorMatch = field.match(/^evaluators\.(.+)\.[^.]+$/);
  if (evaluatorMatch) return `evaluator-${evaluatorMatch[1]}`;
  return undefined;
};

// Seeds the table's (multi-column) initial sort from the group's default_sort — a comma-separated,
// ordered list of API sort fields — so the column headers reflect the saved order on load.
const seedSortFromDefault = (
  defaultSort: string | null | undefined
): { id: string; desc: boolean }[] | undefined => {
  if (!defaultSort) return undefined;
  const entries = defaultSort
    .split(',')
    .map((token) => token.trim())
    .filter(Boolean)
    .map((token) => {
      const desc = token.startsWith('-');
      const id = sortFieldToColumnId(desc ? token.slice(1) : token);
      return id ? { id, desc } : undefined;
    })
    .filter((entry): entry is { id: string; desc: boolean } => entry !== undefined);
  return entries.length ? entries : undefined;
};

// Maps a filter column id to its dotted API rollup-stat field (required by the backend parser).
// Evaluator ids are dynamic, so derive `evaluators.<name>.mean` here, like getEvaluationSortParam.
const getEvaluationFilterField = (id: string): string | undefined => {
  if (id === 'cost_usd') return 'cost_usd.mean';
  if (id === 'latency_ms') return 'latency_ms.mean';
  const evaluatorMatch = id.match(/^evaluator-(.+)$/);
  if (evaluatorMatch) return `evaluators.${evaluatorMatch[1]}.mean`;
  return undefined;
};

// Resolves one sorting-state entry to its API sort field (with '-' prefix for descending), or
// undefined when the column has no corresponding API sort field.
const resolveEvaluationSortField = (entry: { id: string; desc: boolean }): string | undefined => {
  let field = STATIC_SORT_FIELD_MAP[entry.id];
  if (!field) {
    // Evaluator columns use id `evaluator-<name>` so the API field can be derived without
    // a separate lookup into evaluatorNames (which would create a circular dependency).
    const evaluatorMatch = entry.id.match(/^evaluator-(.+)$/);
    if (evaluatorMatch) field = `evaluators.${evaluatorMatch[1]}.mean`;
  }
  if (!field) return undefined;
  return `${entry.desc ? '-' : ''}${field}`;
};

// Emits the API `sort` param from the table's (multi-column) sorting state: a comma-separated,
// ordered list of fields — the first sorted column dominates, matching the API's key precedence.
const getEvaluationSortParam = (
  sortingState: { id: string; desc: boolean }[]
): ListEvaluationsSortParam | undefined => {
  // No column sort -> omit `sort`; the API then defaults to -created_at with pinned first.
  if (sortingState.length === 0) return undefined;
  const fields = sortingState
    .map(resolveEvaluationSortField)
    .filter((field): field is string => field !== undefined);
  if (fields.length === 0) return DEFAULT_SORT;
  return fields.join(',') as ListEvaluationsSortParam;
};

interface ExperimentGroupDataViewProps {
  /** The loaded group, so the table's initial sort can seed from `default_sort` at first
   * render — the sorting state is initialized once and not reactive. */
  group: ExperimentGroupResponse;
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
export const ExperimentGroupDataView: FC<ExperimentGroupDataViewProps> = ({ group }) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const toast = useToast();
  const experimentGroupName = group.name;
  const experimentGroupId = group.id;

  // Persist column order to localStorage, keyed by experiment group ID.
  const [savedColumnOrder, saveColumnOrder] = useLocalStorage<string[]>(
    `nemo-studio:experiment-group-columns:${experimentGroupId}`,
    []
  );

  // Seed the sort from default_sort so its column header reflects the order on load. Memoized so the
  // reference is stable across renders (until default_sort changes).
  const defaultSort = useMemo(() => seedSortFromDefault(group.default_sort), [group.default_sort]);

  const dataViewState = useStudioDataViewState<EvaluationFilter>({
    defaultSort,
    // The evaluations leaderboard supports multi-column sort (shift-click) — score vs. cost etc.
    multiSort: true,
    columnVisibility: { created_by: false, updated_at: false },
    // Keep the pin toggle reachable while horizontally scrolling this wide table.
    columnPinning: { left: ['pin'] },
    filterFieldMap: getEvaluationFilterField,
    columnOrder: savedColumnOrder ?? [],
  });

  // Write column order to localStorage whenever it changes after the first reorder.
  const { columnOrder } = dataViewState;
  useEffect(() => {
    if (columnOrder.state.length > 0) saveColumnOrder(columnOrder.state);
  }, [columnOrder.state, saveColumnOrder]);

  const page = dataViewState.pagination.state.pageIndex + 1;
  const pageSize = dataViewState.pagination.state.pageSize;
  const sortParam = getEvaluationSortParam(dataViewState.sorting.state);

  const {
    rows: orderedData,
    togglePin,
    totalCount,
    error,
    isLoading,
    isSuccess,
  } = useExperimentGroupEvaluations({
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

  // One score column per evaluator: the names found across the loaded rows, plus any evaluator
  // with an active filter (so its column survives a zero-result filter — see deriveEvaluatorNames).
  const evaluatorNames = useMemo(
    () => deriveEvaluatorNames(orderedData, dataViewState.debouncedColumnFilters),
    [orderedData, dataViewState.debouncedColumnFilters]
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
    ComponentProps<typeof DataViewRoot<EvaluationRow>>['makeColumns']
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
            <Tooltip
              slotContent={
                <Text kind="body/regular/sm">
                  {isPinned ? 'Unpin for all users' : 'Pin for all users'}
                </Text>
              }
              className={tooltipClassName}
              side="right"
            >
              <Button
                kind="tertiary"
                color="neutral"
                size="small"
                aria-label={isPinned ? 'Unpin evaluation' : 'Pin evaluation'}
                aria-pressed={isPinned}
                onClick={() => togglePin(row.original)}
              >
                <Pin
                  className={isPinned ? 'text-brand' : 'text-secondary'}
                  {...(isPinned ? { fill: 'currentColor' } : {})}
                />
              </Button>
            </Tooltip>
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
          const { name, description } = row.original;
          if (!description) return <Text>{name}</Text>;
          return (
            <Tooltip
              slotContent={
                <div className="flex flex-col gap-1">
                  <Text kind="label/regular/sm" className="text-secondary">
                    Description
                  </Text>
                  <Text kind="body/regular/sm">{description}</Text>
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
          meta: { title: false, filter: numberRangeFilter(`Avg ${title}`) },
          size: 140,
          cell: ({ row }) => {
            const score = row.original.aggregate_scores?.[name];
            return (
              <MeanValueTooltipCell
                label={title}
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
        meta: { title: false, filter: numberRangeFilter('Avg Cost') },
        cell: ({ row }) => {
          const { cost_usd, run_count } = row.original;
          return (
            <MeanValueTooltipCell label="cost" count={cost_usd?.count} runCount={run_count}>
              {cost_usd?.mean != null ? `$${cost_usd.mean.toFixed(3)}` : '-'}
            </MeanValueTooltipCell>
          );
        },
      }),
      accessor((original) => original.latency_ms?.mean, {
        id: 'latency_ms',
        header: 'Avg Latency',
        meta: { title: false, filter: numberRangeFilter('Avg Latency') },
        enableSorting: true,
        cell: ({ row }) => {
          const { latency_ms, run_count } = row.original;
          return (
            <MeanValueTooltipCell label="latency" count={latency_ms?.count} runCount={run_count}>
              {latency_ms?.mean != null ? formatDurationMs(latency_ms.mean) : '-'}
            </MeanValueTooltipCell>
          );
        },
      }),
      accessor((original) => original.test_case_count, {
        id: 'test_case_count',
        header: 'Total test cases',
        enableSorting: true,
        cell: ({ row }) => <Text>{String(row.original.test_case_count ?? 0)}</Text>,
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
        navigate(getEvaluationDetailRoute(workspace, experimentGroupName, row.name))
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
          requestStatus: isLoading ? 'loading' : undefined,
        },
        DataViewTableContent: {
          enableColumnReordering: true,
          renderEmptyState: ({ hasFiltersApplied, hasSearchApplied }) =>
            hasFiltersApplied || hasSearchApplied ? null : (
              <Empty experimentGroupName={experimentGroupName} />
            ),
        },
      }}
    />
  );
};
