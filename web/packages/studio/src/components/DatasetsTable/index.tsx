// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { Button } from '@nvidia/foundations-react-core';
import { DatasetCreateModal } from '@studio/components/DatasetCreateModal';
import { DatasetCreateModalMode } from '@studio/components/DatasetCreateModal/constants';
import { makeDatasetsTableColumns } from '@studio/components/DatasetsTable/columns';
import { type DatasetsTableProps } from '@studio/components/DatasetsTable/types';
import { useDatasetsTable } from '@studio/components/DatasetsTable/useDatasetsTable';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { Loading } from '@studio/components/Layouts/Loading';
import { NewDatasetButton } from '@studio/components/NewDatasetButton';
import { NewModelFilesetButton } from '@studio/components/NewModelFilesetButton';
import { FILESET_DETAILS_ENABLED } from '@studio/constants/environment';
import { LINK_DOCS_DATASETS } from '@studio/constants/links';
import { DatasetBulkDeleteModal } from '@studio/routes/FilesetListRoute/DatasetBulkDeleteModal';
import { getNewFilesetRoute } from '@studio/routes/utils';
import { X, Database, Trash } from 'lucide-react';
import { type FC } from 'react';
import { Link } from 'react-router-dom';

export type { DatasetsTableProps } from '@studio/components/DatasetsTable/types';

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
  attributes,
}) => {
  const {
    workspace,
    dataViewState,
    hasSearchOrFilters,
    modalDataset,
    setModalDataset,
    modalOpen,
    setModalOpen,
    datasetsResponse,
    datasets,
    refetch,
    isPending,
    isFetching,
    error,
    resetFilters,
    handleRowClick,
    handleDatasetDeleted,
    handleDeleteDataset,
    handleBulkDeleteSuccess,
    handleModalClose,
  } = useDatasetsTable({
    onDatasetsSelected,
    onRowClick,
    enableFilters,
    enableSelection,
    selectionType,
    getDatasetRoute,
    purposeFilter,
  });

  // Column definitions
  const makeColumns = makeDatasetsTableColumns({
    enableSelection,
    selectionType,
    enableFilters,
    enableActions,
    getDatasetRoute,
    renderRowActions,
    setModalDataset,
    setModalOpen,
    handleDatasetDeleted,
  });

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
          ...attributes,
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
                      {FILESET_DETAILS_ENABLED ? (
                        <>
                          <NewDatasetButton />
                          <NewModelFilesetButton />
                        </>
                      ) : (
                        <Button asChild color="brand">
                          <Link to={getNewFilesetRoute(workspace)}>Create Fileset</Link>
                        </Button>
                      )}
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
