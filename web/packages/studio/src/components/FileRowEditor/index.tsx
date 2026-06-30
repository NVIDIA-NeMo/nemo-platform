// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Button, Flex, Stack, Tag, Text } from '@nvidia/foundations-react-core';
import { makeDataFileColumns } from '@studio/components/FileRowEditor/columns';
import { FILE_FORMAT_TAG_COLOR } from '@studio/components/FileRowEditor/constants';
import {
  formatFromFileName,
  parseDataFile,
  TEXT_PARSEABLE_FORMATS,
  type DataFileFormat,
} from '@studio/components/FileRowEditor/parse';
import { RowEditorPanel } from '@studio/components/FileRowEditor/RowEditorPanel';
import {
  compareValues,
  defaultValueForType,
  inferColumns,
} from '@studio/components/FileRowEditor/schema';
import {
  ROW_ID_KEY,
  type DataFileColumn,
  type DataFileRow,
} from '@studio/components/FileRowEditor/types';
import { Download, FileSpreadsheet, FolderOpen, Plus, Trash } from 'lucide-react';
import { type ChangeEvent, type FC, useCallback, useMemo, useRef, useState } from 'react';

// Stable references so the data-view hook's memoized state doesn't churn each render.
// Sort by the synthetic row id by default to preserve load order regardless of schema.
const DEFAULT_SORT = { id: ROW_ID_KEY, desc: false };
const COLUMN_PINNING = { left: ['row-selection'], right: ['row-actions'] };

/** Reads a row's stable identity. */
const rowId = (row: DataFileRow): number => row[ROW_ID_KEY] as number;

/** Assigns stable, sequential identities to freshly-loaded rows. */
const assignRowIds = (rows: DataFileRow[]): DataFileRow[] =>
  rows.map((row, index) => ({ ...row, [ROW_ID_KEY]: index + 1 }));

const cloneRow = (row: DataFileRow): DataFileRow => {
  try {
    return structuredClone(row);
  } catch {
    return JSON.parse(JSON.stringify(row)) as DataFileRow;
  }
};

const nextId = (rows: DataFileRow[]): number =>
  rows.reduce((max, row) => Math.max(max, rowId(row) || 0), 0) + 1;

/** Builds a blank row from the schema, with type-appropriate empty values. */
const emptyRow = (id: number, columns: DataFileColumn[]): DataFileRow => {
  const row: DataFileRow = { [ROW_ID_KEY]: id };
  for (const column of columns) {
    // Enum columns start on their first allowed value so the select isn't blank.
    row[column.key] =
      column.type === 'string' && column.options?.length
        ? column.options[0]
        : defaultValueForType(column.type);
  }
  return row;
};

/**
 * StudioDataView runs in `manual` mode (manual filtering/sorting/pagination), so the
 * consumer must derive the page slice itself. This applies the data view's search,
 * column filters, and sorting to in-memory rows — generically, across whatever columns
 * the data happens to have.
 */
const deriveRows = (
  rows: DataFileRow[],
  {
    search,
    columnFilters,
    sorting,
  }: {
    search: string;
    columnFilters: { id: string; value: unknown }[];
    sorting: { id: string; desc: boolean }[];
  }
): DataFileRow[] => {
  let result = rows;

  const query = search.trim().toLowerCase();
  if (query) {
    result = result.filter((row) =>
      Object.keys(row).some(
        (key) =>
          key !== ROW_ID_KEY &&
          String(row[key] ?? '')
            .toLowerCase()
            .includes(query)
      )
    );
  }

  for (const { id, value } of columnFilters) {
    if (value === undefined || value === null || value === '') {
      continue;
    }
    result = result.filter((row) => String(row[id] ?? '') === String(value));
  }

  if (sorting.length > 0) {
    const { id, desc } = sorting[0];
    result = [...result].sort((a, b) => {
      const cmp = compareValues(a[id], b[id]);
      return desc ? -cmp : cmp;
    });
  }

  return result;
};

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ['KB', 'MB', 'GB'];
  let size = bytes / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit++;
  }
  return `${size.toFixed(1)} ${units[unit]}`;
};

export interface FileRowEditorProps {
  /** File name shown in the header. Its extension drives the format chip. */
  fileName?: string;
  /** File size label shown in the header summary. */
  fileSizeLabel?: string;
  /**
   * Column schema. When omitted, it is inferred from {@link initialRows} — this is the
   * common path. Provide it to control order/labels/types or to support an empty file.
   */
  columns?: DataFileColumn[];
  /** Initial dataset rows of any row-like shape. */
  initialRows?: DataFileRow[];
  /**
   * Whether to show the "Open File" action that loads a local file in-browser. Disable
   * when rows are supplied by the host (e.g. fetched from the Files API) so the user can't
   * swap in an unrelated local file. @defaultValue true
   */
  showOpenFile?: boolean;
  className?: string;
}

/**
 * Data File — Row Viewer / Editor.
 *
 * A `StudioDataView` table for a structured data file (Parquet/CSV/JSON/JSONL) paired
 * with a `SidePanel` row editor. The schema is inferred from the data (or supplied via
 * `columns`), so the viewer works for any row-like file rather than one fixed shape.
 * Self-contained and presentational: it owns its row state in memory and can open a
 * local JSON/JSONL/CSV file in the browser. Wire `initialRows`/`columns` and the row
 * handlers to the Files API to go live.
 */
export const FileRowEditor: FC<FileRowEditorProps> = ({
  fileName: fileNameProp = 'qa-sft-dataset-v1.parquet',
  fileSizeLabel: fileSizeLabelProp = '4.2 MB',
  columns: columnsProp,
  initialRows = [],
  showOpenFile = true,
  className,
}) => {
  const toast = useToast();
  const [rows, setRows] = useState<DataFileRow[]>(() => assignRowIds(initialRows));
  const [columns, setColumns] = useState<DataFileColumn[]>(
    () => columnsProp ?? inferColumns(initialRows)
  );
  const [fileName, setFileName] = useState(fileNameProp);
  const [fileSizeLabel, setFileSizeLabel] = useState(fileSizeLabelProp);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<DataFileRow | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fileFormat: DataFileFormat = useMemo(() => formatFromFileName(fileName), [fileName]);

  const dataViewState = useStudioDataViewState({
    defaultPageSize: 10,
    defaultSort: DEFAULT_SORT,
    columnPinning: COLUMN_PINNING,
  });

  const { debouncedSearchBar, debouncedColumnFilters } = dataViewState;
  const sorting = dataViewState.sorting.state;
  const { pageIndex, pageSize } = dataViewState.pagination.state;

  const processedRows = useMemo(
    () =>
      deriveRows(rows, {
        search: debouncedSearchBar,
        columnFilters: debouncedColumnFilters,
        sorting,
      }),
    [rows, debouncedSearchBar, debouncedColumnFilters, sorting]
  );
  // The hook resets pagination to page 1 when search/filters change; clamp the slice so
  // shrinking results (e.g. after a delete) never render an out-of-range empty page.
  const lastPageIndex = Math.max(0, Math.ceil(processedRows.length / pageSize) - 1);
  const safePageIndex = Math.min(pageIndex, lastPageIndex);
  const pageRows = useMemo(
    () => processedRows.slice(safePageIndex * pageSize, safePageIndex * pageSize + pageSize),
    [processedRows, safePageIndex, pageSize]
  );

  const committedRow =
    editingId === null ? null : (rows.find((row) => rowId(row) === editingId) ?? null);
  const editingIndex = editingId === null ? -1 : rows.findIndex((row) => rowId(row) === editingId);
  const isDirty =
    !!draft && !!committedRow && JSON.stringify(draft) !== JSON.stringify(committedRow);

  const openEditorRow = useCallback((row: DataFileRow) => {
    setEditingId(rowId(row));
    setDraft(cloneRow(row));
  }, []);

  const closeEditor = useCallback(() => {
    // Keep `draft` so the close animation still shows content; the next open replaces it.
    setEditingId(null);
  }, []);

  const deleteRowById = useCallback((id: number) => {
    setRows((prev) => prev.filter((row) => rowId(row) !== id));
    setEditingId((prev) => (prev === id ? null : prev));
  }, []);

  const duplicateRow = useCallback((row: DataFileRow) => {
    setRows((prev) => {
      const index = prev.findIndex((entry) => rowId(entry) === rowId(row));
      if (index === -1) {
        return prev;
      }
      const copy = { ...cloneRow(row), [ROW_ID_KEY]: nextId(prev) };
      const next = [...prev];
      next.splice(index + 1, 0, copy);
      return next;
    });
  }, []);

  const makeColumns = useMemo(
    () =>
      makeDataFileColumns(columns, {
        onEdit: openEditorRow,
        onDuplicate: duplicateRow,
        onDelete: (row) => deleteRowById(rowId(row)),
      }),
    [columns, openEditorRow, duplicateRow, deleteRowById]
  );

  const handleFieldChange = useCallback((key: string, value: unknown) => {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
  }, []);

  const handleSave = () => {
    if (!draft) {
      return;
    }
    setRows((prev) => prev.map((row) => (rowId(row) === rowId(draft) ? cloneRow(draft) : row)));
    setEditingId(null);
    toast.success('Row saved successfully');
  };

  const handleAddRow = () => {
    const created = emptyRow(nextId(rows), columns);
    setRows((prev) => [...prev, created]);
    openEditorRow(created);
  };

  const navigateEditor = (delta: number) => {
    const target = rows[editingIndex + delta];
    if (target) {
      openEditorRow(target);
    }
  };

  const handleOpenFileClick = () => fileInputRef.current?.click();

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input so selecting the same file again re-triggers change.
    event.target.value = '';
    if (!file) {
      return;
    }

    const format = formatFromFileName(file.name);
    if (!TEXT_PARSEABLE_FORMATS.includes(format)) {
      setLoadError(
        format === 'parquet'
          ? 'Parquet is binary — load it through the Files API. In-browser open supports JSON, JSONL & CSV.'
          : `Unsupported file type: ${file.name}`
      );
      return;
    }

    try {
      const text = await file.text();
      const parsed = assignRowIds(parseDataFile(text, format));
      setRows(parsed);
      setColumns(inferColumns(parsed));
      setFileName(file.name);
      setFileSizeLabel(formatBytes(file.size));
      setEditingId(null);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Failed to parse file.');
    }
  };

  return (
    <Stack gap="density-xl" className={`h-full w-full min-w-0 ${className ?? ''}`}>
      {/* File header */}
      <Flex align="center" gap="density-md" className="w-full shrink-0">
        <Flex
          align="center"
          justify="center"
          className="size-10 shrink-0 rounded-md bg-surface-sunken"
        >
          <FileSpreadsheet size={20} className="text-secondary" />
        </Flex>
        <Stack gap="density-xs" className="min-w-0 flex-1">
          <Flex align="center" gap="density-sm">
            <Text kind="title/xs" className="truncate">
              {fileName}
            </Text>
            <Tag kind="solid" color={FILE_FORMAT_TAG_COLOR[fileFormat]} readOnly>
              {fileFormat === 'unknown' ? 'FILE' : fileFormat.toUpperCase()}
            </Tag>
          </Flex>
          <Flex align="center" gap="density-sm" className="text-secondary">
            <Text kind="body/regular/sm" className="text-secondary">
              {rows.length.toLocaleString()} rows · {columns.length} columns · {fileSizeLabel}
            </Text>
            <Text kind="body/regular/sm" className="text-secondary">
              ·
            </Text>
            {loadError ? (
              <Text kind="body/regular/sm" className="text-danger">
                {loadError}
              </Text>
            ) : (
              <Text kind="body/regular/sm" className="text-secondary">
                Schema inferred
              </Text>
            )}
          </Flex>
        </Stack>
        <Flex align="center" gap="density-sm" className="shrink-0">
          {showOpenFile && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,.jsonl,.ndjson,.csv"
                className="hidden"
                aria-hidden="true"
                tabIndex={-1}
                onChange={handleFileSelected}
              />
              <Button kind="secondary" color="neutral" onClick={handleOpenFileClick}>
                <FolderOpen size={16} />
                Open File
              </Button>
            </>
          )}
          <Button kind="secondary" color="neutral">
            <Download size={16} />
            Download
          </Button>
          <Button kind="primary" color="brand" onClick={handleAddRow}>
            <Plus size={16} />
            Add Row
          </Button>
        </Flex>
      </Flex>

      {/* Table */}
      <Stack className="min-h-0 min-w-0 w-full flex-1">
        <StudioDataView<DataFileRow>
          dataViewState={dataViewState}
          makeColumns={makeColumns}
          searchField={columns.length > 0 ? columns[0].key : undefined}
          onRowClick={openEditorRow}
          renderBulkActions={({ selectedRows }) => (
            <Button
              kind="tertiary"
              color="danger"
              onClick={() => selectedRows.forEach((row) => deleteRowById(rowId(row)))}
            >
              <Trash size={16} />
              Delete ({selectedRows.length})
            </Button>
          )}
          attributes={{
            DataViewRoot: { data: pageRows, totalCount: processedRows.length },
            DataViewSearchBar: { placeholder: 'Search rows…' },
          }}
        />
      </Stack>

      <RowEditorPanel
        open={editingId !== null}
        columns={columns}
        draft={draft}
        rowNumber={editingIndex + 1}
        totalRows={rows.length}
        isDirty={isDirty}
        onFieldChange={handleFieldChange}
        onClose={closeEditor}
        onPrev={() => navigateEditor(-1)}
        onNext={() => navigateEditor(1)}
        onDelete={() => editingId !== null && deleteRowById(editingId)}
        onSave={handleSave}
      />
    </Stack>
  );
};
