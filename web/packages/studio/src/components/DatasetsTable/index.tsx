// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import {
  ROW_ACTIONS_COLUMN_SIZE,
  ROW_SELECTION_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { getSortParam } from '@nemo/common/src/utils/query';
import { useFilesDeleteFileset, useFilesListFilesets } from '@nemo/sdk/generated/platform/api';
import {
  FilesetPurpose,
  StorageConfigType,
  type FilesetOutput as Dataset,
  type GenericSortField,
  type HuggingfaceStorageConfig,
  type LocalStorageConfig,
  type NGCStorageConfig,
  type S3StorageConfig,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Text } from '@nvidia/foundations-react-core';
import { invalidateDatasetCaches } from '@studio/api/datasets/invalidateDatasetCaches';
import { DatasetCreateModal } from '@studio/components/DatasetCreateModal';
import { DatasetCreateModalMode } from '@studio/components/DatasetCreateModal/constants';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { Loading } from '@studio/components/Layouts/Loading';
import { NewDatasetButton } from '@studio/components/NewDatasetButton';
import { NewModelFilesetButton } from '@studio/components/NewModelFilesetButton';
import { FILESET_DETAILS_ENABLED } from '@studio/constants/environment';
import { LINK_DOCS_DATASETS } from '@studio/constants/links';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { DatasetBulkDeleteModal } from '@studio/routes/FilesetListRoute/DatasetBulkDeleteModal';
import { formatStorageBackendLabel, type StorageBackend } from '@studio/util/storageBackend';
import { keepPreviousData } from '@tanstack/react-query';
import { Cloud, X, Database, Trash } from 'lucide-react';
import {
  type ComponentProps,
  type FC,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';

type ModalOpenState = 'delete' | 'edit' | 'none';

type StorageConfig =
  | LocalStorageConfig
  | NGCStorageConfig
  | HuggingfaceStorageConfig
  | S3StorageConfig;

function getStorageBackend(storage: StorageConfig | undefined): StorageBackend | null {
  return storage?.type ?? null;
}

const PURPOSE_LABELS: Record<FilesetPurpose, string> = {
  [FilesetPurpose.generic]: 'Generic',
  [FilesetPurpose.dataset]: 'Dataset',
  [FilesetPurpose.model]: 'Model',
};

function getStoragePath(storage: StorageConfig | undefined): string | null {
  if (!storage) return null;
  const s = storage as {
    type?: string;
    path?: string;
    org?: string;
    team?: string;
    target?: string;
    repo_id?: string;
    bucket?: string;
    prefix?: string;
  };
  if (s.type === 'local' && 'path' in storage) {
    return (storage as LocalStorageConfig).path;
  }
  if (s.type === 'ngc' && 'org' in storage && 'team' in storage && 'target' in storage) {
    const ngc = storage as NGCStorageConfig;
    return `${ngc.org}/${ngc.team}/${ngc.target}`;
  }
  if (s.type === 'huggingface' && 'repo_id' in storage) {
    return (storage as HuggingfaceStorageConfig).repo_id;
  }
  if (s.type === 's3' && 'bucket' in storage) {
    const s3 = storage as S3StorageConfig;
    return s3.prefix ? `${s3.bucket}/${s3.prefix}` : s3.bucket;
  }
  return null;
}

export interface DatasetsTableProps {
  /** Callback when datasets are selected */
  onDatasetsSelected?: (datasets: Dataset[]) => void;
  /** Callback when a row is clicked */
  onRowClick?: (dataset: Dataset) => void;
  /** Disable row actions (default: true) */
  enableActions?: boolean;
  /** Enable bulk delete when items selected (default: false) */
  enableBulkDelete?: boolean;
  /** Enable search bar and filters (default: false) */
  enableFilters?: boolean;
  /** Enable checkbox selection (default: true) */
  enableSelection?: boolean;
  /** Type of selection (default: 'multiple') */
  selectionType?: 'multiple' | 'single';
  /** Render dataset name as link - provide a function that returns the route */
  getDatasetRoute?: (dataset: Dataset) => string;
  /** When set, restricts the fetched filesets to the given purpose. Pass FilesetPurpose.dataset in picker contexts that are specifically designed for dataset inputs. */
  purposeFilter?: FilesetPurpose;
  /** Custom render for row actions */
  renderRowActions?: (
    dataset: Dataset,
    callbacks: {
      onNavigate: () => void;
      onEdit: () => void;
      onDelete: () => void;
      onDatasetDeleted: (dataset: Dataset) => void;
    }
  ) => ReactNode;
  attributes?: {
    DataViewRoot?: ComponentProps<typeof DataView.Root<DatasetWithId>> & { dataMode: 'manual' };
    DataViewContent?: ComponentProps<typeof DataView.TableContent>;
  };
}

type DatasetWithId = Dataset & { id: string };

/**
 * A table that displays a list of datasets with optional filtering, search, and bulk operations.
 */
export const DatasetsTable: FC<DatasetsTableProps> = ({
  onDatasetsSelected,
  onRowClick,
  enableActions = true,
  enableBulkDelete,
  enableFilters,
  enableSelection,
  selectionType,
  getDatasetRoute,
  renderRowActions,
  purposeFilter,
}) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();

  // DataView state for pagination, row selection, sorting, search, and filters
  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  const hasActiveFilters = dataViewState.debouncedColumnFilters.length > 0;
  const hasSearchOrFilters = !!(dataViewState.debouncedSearchBar || hasActiveFilters);

  const [modalDataset, setModalDataset] = useState<Dataset>();
  const [modalOpen, setModalOpen] = useState<ModalOpenState>();
  const { mutateAsync: deleteDataset } = useFilesDeleteFileset({
    mutation: {
      onSuccess: (_data, variables) => {
        invalidateDatasetCaches(variables.workspace, variables.name, ['list']);
      },
    },
  });

  // Reset filters and selections
  const resetFilters = useCallback(() => {
    onDatasetsSelected?.([]);
    dataViewState.resetFilters();
  }, [dataViewState, onDatasetsSelected]);

  const {
    data: datasetsResponse,
    refetch,
    isPending,
    isFetching,
    error,
  } = useFilesListFilesets(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: enableFilters
        ? (getSortParam(dataViewState.sorting.state) as GenericSortField)
        : undefined,
      filter: {
        ...(enableFilters ? dataViewState.apiFilter.filter : undefined),
        ...(purposeFilter !== undefined ? { purpose: purposeFilter } : {}),
      },
    },
    {
      query: {
        placeholderData: keepPreviousData,
      },
    }
  );

  // Ensure each dataset has a unique id for DataView row selection
  const datasets = useMemo<DatasetWithId[]>(
    () =>
      (datasetsResponse?.data || []).map((dataset) => ({
        ...dataset,
        id: dataset.id || `${dataset.workspace}/${dataset.name}`,
      })),
    [datasetsResponse?.data]
  );

  // Propagate row selection changes to onDatasetsSelected callback
  const prevSelectionRef = useRef(dataViewState.rowSelection.state);
  useEffect(() => {
    const selection = dataViewState.rowSelection.state;
    if (selection === prevSelectionRef.current) return;
    prevSelectionRef.current = selection;

    if (!onDatasetsSelected) return;

    // For single selection, keep only the most recently selected row
    const selectedIds = Object.keys(selection).filter((id) => selection[id]);
    if (selectionType === 'single' && selectedIds.length > 1) {
      const lastSelected = selectedIds[selectedIds.length - 1];
      dataViewState.rowSelection.set({ [lastSelected]: true });
      return; // The set above will re-trigger this effect with the corrected state
    }

    const selectedDatasets = datasets.filter((d) => selection[d.id]);
    onDatasetsSelected(selectedDatasets);
  }, [
    dataViewState.rowSelection.state,
    datasets,
    onDatasetsSelected,
    selectionType,
    dataViewState.rowSelection,
  ]);

  // Row click handler
  const handleRowClick = useCallback(
    (dataset: DatasetWithId) => {
      if (onRowClick) {
        onRowClick(dataset);
      }
      if (getDatasetRoute) {
        navigate(getDatasetRoute(dataset));
      }
      if (enableSelection && !enableFilters) {
        // In simple mode, clicking row selects it
        dataViewState.rowSelection.set({ [dataset.id]: true });
      }
    },
    [
      onRowClick,
      getDatasetRoute,
      navigate,
      enableSelection,
      enableFilters,
      dataViewState.rowSelection,
    ]
  );

  // Action handlers
  const handleDatasetDeleted = useCallback(
    (deletedDataset: Dataset) => {
      const currentSelection = { ...dataViewState.rowSelection.state };
      delete currentSelection[deletedDataset.id || ''];
      dataViewState.rowSelection.set(currentSelection);
    },
    [dataViewState.rowSelection]
  );

  const handleDeleteDataset = async () => {
    try {
      if (!modalDataset?.workspace || !modalDataset?.name) return false;
      await deleteDataset({
        workspace: modalDataset.workspace,
        name: modalDataset.name,
      });
      handleDatasetDeleted(modalDataset);
      return true;
    } catch {
      return false;
    }
  };

  const handleBulkDeleteSuccess = useCallback(() => {
    onDatasetsSelected?.([]);
    dataViewState.rowSelection.set({});
    refetch();
  }, [dataViewState.rowSelection, onDatasetsSelected, refetch]);

  const handleModalClose = () => setModalOpen('none');

  // Column definitions
  const makeColumns: ComponentProps<typeof DataView.Root<DatasetWithId>>['makeColumns'] = (
    { accessor },
    { rowSelectionColumn, rowActionsColumn }
  ) =>
    [
      enableSelection &&
        rowSelectionColumn({
          size: ROW_SELECTION_COLUMN_SIZE,
          ...(selectionType === 'single' && {
            headerProps: { className: 'invisible' },
          }),
        }),
      accessor('name', {
        header: 'Name',
        enableSorting: enableFilters,
        size: 175,
      }),
      accessor((row) => getStorageBackend(row.storage), {
        id: 'storage_type',
        header: 'Storage Backend',
        size: 130,
        meta: {
          filter: {
            label: 'Storage Backend',
            type: 'single-select',

            options: [
              { value: '', label: 'All' },
              { value: StorageConfigType.local, label: 'Local' },
              { value: StorageConfigType.ngc, label: 'NGC' },
              { value: StorageConfigType.huggingface, label: 'Hugging Face' },
              { value: StorageConfigType.s3, label: 'S3' },
            ],
          },
        },
        cell({ row }) {
          const backend = getStorageBackend(row.original?.storage);
          if (!backend) return null;
          const label = formatStorageBackendLabel(backend);
          const isLocal = backend === 'local';
          const Icon = isLocal ? Database : Cloud;
          return (
            <Flex align="center" gap="density-sm" className="min-w-0">
              <Icon className="flex-none text-fg-subdued" size="16" strokeWidth={0} />
              <Text className="truncate" title={label ?? undefined}>
                {label}
              </Text>
            </Flex>
          );
        },
      }),
      accessor((row) => row.purpose, {
        id: 'purpose',
        header: 'Purpose',
        size: 110,
        meta: {
          filter: {
            label: 'Purpose',
            type: 'single-select',
            options: [
              { value: '', label: 'All' },
              { value: FilesetPurpose.generic, label: 'Generic' },
              { value: FilesetPurpose.dataset, label: 'Dataset' },
              { value: FilesetPurpose.model, label: 'Model' },
            ],
          },
        },
        cell({ row }) {
          const purpose = row.original?.purpose;
          return purpose ? <Text>{PURPOSE_LABELS[purpose] ?? purpose}</Text> : null;
        },
      }),
      accessor((row) => getStoragePath(row.storage), {
        id: 'path',
        header: 'Path',
        size: 200,
        cell({ row }) {
          const path = getStoragePath(row.original?.storage);
          return path ? (
            <Text className="truncate" title={path}>
              {path}
            </Text>
          ) : null;
        },
      }),
      accessor('description', {
        header: 'Description',
        cell({ row }) {
          return (
            <Text className="truncate" title={row.original?.description}>
              {row.original?.description}
            </Text>
          );
        },
      }),
      accessor('created_at', {
        id: 'created_at',
        header: 'Created',
        enableSorting: enableFilters,
        size: 150,
        maxSize: 150,
        minSize: 150,
        meta: {
          filter: dateTimeFilter('Created At'),
        },
        cell({ row }) {
          return row.original?.created_at ? (
            <RelativeTime datetime={row.original.created_at} />
          ) : null;
        },
      }),
      enableActions &&
        rowActionsColumn({
          size: ROW_ACTIONS_COLUMN_SIZE,
          enableResizing: false,
          rowActions: (data: DatasetWithId) => [
            ...(getDatasetRoute
              ? [
                  {
                    children: 'View',
                    onSelect: () => {
                      // Navigation handled by Link
                    },
                  },
                ]
              : []),
            {
              children: 'Edit',
              onSelect: () => {
                setModalDataset(data);
                setModalOpen('edit');
              },
            },
            {
              children: 'Delete',
              danger: true,
              onSelect: () => {
                setModalDataset(data);
                setModalOpen('delete');
              },
            },
          ],
          cell: renderRowActions
            ? ({ row }) => (
                <Flex justify="center" align="center">
                  {renderRowActions(row.original, {
                    onNavigate: () => {
                      /* handled by Link */
                    },
                    onEdit: () => {
                      setModalDataset(row.original);
                      setModalOpen('edit');
                    },
                    onDelete: () => {
                      setModalDataset(row.original);
                      setModalOpen('delete');
                    },
                    onDatasetDeleted: handleDatasetDeleted,
                  })}
                </Flex>
              )
            : undefined,
        }),
    ].filter((col): col is DataView.TanstackTable.ColumnDef<DatasetWithId> => Boolean(col));

  // Loading state
  if (isPending) {
    return <Loading description="Loading filesets..." />;
  }

  // Error state
  if (error) {
    return (
      <ErrorMessage
        message="Failed to fetch filesets"
        slotFooter={
          <Button type="button" kind="tertiary" onClick={() => refetch()}>
            Retry
          </Button>
        }
      />
    );
  }

  // Table content
  const tableContent = (
    <>
      <StudioDataView
        dataViewState={dataViewState}
        searchField={enableFilters ? 'name' : undefined}
        makeColumns={makeColumns}
        onRowClick={handleRowClick}
        renderBulkActions={
          enableBulkDelete
            ? ({ selectedRows }) => (
                <DatasetBulkDeleteModal
                  selectedDatasets={selectedRows}
                  onConfirmSuccess={handleBulkDeleteSuccess}
                  slotTrigger={
                    <Button kind="tertiary">
                      <Trash />
                      Delete
                    </Button>
                  }
                />
              )
            : undefined
        }
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search filesets...',
          },
          DataViewRoot: {
            data: datasets,
            totalCount: datasetsResponse?.pagination?.total_results,
            requestStatus: isFetching ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasSearchOrFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No filesets match your filters"
                  actions={
                    <Button kind="tertiary" onClick={resetFilters}>
                      <X /> Clear Filters
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  header="Manage Filesets"
                  emptyMessage="Create a fileset to upload training data, models, or other files. Choose a purpose — Generic, Dataset, or Model — to control which metadata is available."
                  icon={<Database className="size-12 text-fg-subdued" aria-hidden />}
                  actions={
                    <>
                      <DocumentationButton href={LINK_DOCS_DATASETS} />
                      <NewDatasetButton />
                      {FILESET_DETAILS_ENABLED && <NewModelFilesetButton />}
                    </>
                  }
                />
              ),
          },
        }}
      />

      {modalOpen === 'delete' && modalDataset && (
        <DeleteConfirmationModal
          open
          simpleConfirm
          onDelete={handleDeleteDataset}
          title={`Delete Dataset: ${modalDataset.name}`}
          confirmationText={modalDataset.name ?? getEntityReference(modalDataset)}
          onClose={handleModalClose}
        />
      )}

      {modalOpen === 'edit' && modalDataset && (
        <DatasetCreateModal
          dataset={modalDataset}
          mode={DatasetCreateModalMode.Edit}
          onClose={handleModalClose}
          open={modalOpen === 'edit'}
        />
      )}
    </>
  );

  return tableContent;
};
