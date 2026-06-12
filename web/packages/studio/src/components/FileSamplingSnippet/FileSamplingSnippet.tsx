// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor, type CodeEditorProps } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import {
  type JsonlObjectSampleRow,
  buildRowsAndKeysFromJsonlSample,
  formatJsonlSampleCellValue,
  labelForJsonlSampleColumnKey,
} from '@nemo/common/src/utils/parseJsonlObjectSample';
import {
  DEFAULT_MAX_FILE_SAMPLE_ROWS,
  type FileSampleMethod,
  sampleTextLines,
} from '@nemo/common/src/utils/sampleTextLines';
import { Banner, Flex, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import classnames from 'classnames';
import {
  type ComponentProps,
  type ComponentPropsWithoutRef,
  type FC,
  type ReactNode,
  useEffect,
  useMemo,
} from 'react';

/** How sampled file rows are presented in the UI. */
export type FileSamplingDisplayMode = 'code' | 'table';

/** Outer shell scrolls; inner StudioDataView owns the table scroll region. */
const DEFAULT_TABLE_SHELL =
  'flex min-w-0 flex-1 flex-col overflow-hidden min-h-[200px] max-h-[min(560px,55vh)]';
const DEFAULT_EDITOR_CLASS = 'min-h-[200px] max-h-[400px]';

function getTablePageSize(maxSampleRows: number): number {
  return Math.min(Math.max(maxSampleRows, 25), 500);
}

export interface FileSamplingSnippetAttributes {
  /**
   * Extra props for table mode: merged into {@link StudioDataView} `attributes.DataViewRoot`
   * (shell sizing classes should go in `className`).
   */
  table?: ComponentPropsWithoutRef<'div'>;
  /** Forwarded to {@link CodeEditor} in code mode (`content` / `contentType` stay controlled here). */
  editor?: Omit<CodeEditorProps, 'content' | 'contentType'>;
  /** Merged into {@link StudioDataView} `attributes` (internal data loading still wins for root data). */
  studioDataView?: Partial<
    NonNullable<ComponentProps<typeof StudioDataView<JsonlObjectSampleRow>>['attributes']>
  >;
}

export interface FileSamplingSnippetProps {
  workspace: string;
  filesetName: string;
  filePath: string;
  /** Maximum number of non-empty lines to include in the sample. */
  maxSampleRows?: number;
  sampleMethod: FileSampleMethod;
  onSampledContentChange: (text: string) => void;
  /** Render JSONL in a code editor (default) or as rows in {@link StudioDataView}. */
  displayMode?: FileSamplingDisplayMode;
  attributes?: FileSamplingSnippetAttributes;
  /** Optional content shown under the editor (e.g. live evaluation limits). */
  slotFooter?: ReactNode;
}

export const FileSamplingSnippet: FC<FileSamplingSnippetProps> = ({
  workspace,
  filesetName,
  filePath,
  maxSampleRows = DEFAULT_MAX_FILE_SAMPLE_ROWS,
  sampleMethod,
  onSampledContentChange,
  displayMode = 'code',
  attributes,
  slotFooter,
}) => {
  const enabled = Boolean(filesetName && filePath);

  const dataViewState = DataView.useDataViewState({
    pagination: {
      pageSize: getTablePageSize(maxSampleRows),
      pageIndex: 0,
    },
  });
  const setTablePagination = dataViewState.pagination.set;
  const tablePageSize = getTablePageSize(maxSampleRows);

  useEffect(() => {
    setTablePagination((prev) => {
      if (prev.pageSize === tablePageSize && prev.pageIndex === 0) {
        return prev;
      }
      return { ...prev, pageSize: tablePageSize, pageIndex: 0 };
    });
  }, [setTablePagination, tablePageSize]);

  const {
    data: fileContent,
    isLoading: isLoadingFileContent,
    isError: isFileContentError,
  } = useDatasetFileContent({
    workspace,
    name: filesetName,
    path: filePath,
    enabled,
  });

  const sampledText = useMemo(() => {
    if (!enabled || isFileContentError || fileContent === undefined) {
      return '';
    }
    return sampleTextLines(fileContent, sampleMethod, maxSampleRows);
  }, [enabled, isFileContentError, fileContent, sampleMethod, maxSampleRows]);

  const { rows: tableRows, columnKeys } = useMemo(
    () => buildRowsAndKeysFromJsonlSample(sampledText),
    [sampledText]
  );

  const makeColumns = useMemo<
    ComponentProps<typeof StudioDataView<JsonlObjectSampleRow>>['makeColumns']
  >(() => {
    return (helpers) => {
      return [
        helpers.accessor('rowIndex', {
          id: '_row',
          header: '#',
          size: 52,
          minSize: 44,
          enableSorting: false,
          enableColumnFilter: false,
          cell: ({ row }) => (
            <Text kind="body/regular/sm" className="tabular-nums text-secondary">
              {row.original.rowIndex}
            </Text>
          ),
        }),
        ...columnKeys.map((key, colIndex) => {
          const fieldKey = key;
          return helpers.accessor((row) => row.values[fieldKey], {
            id: `jsonl-field-${colIndex}`,
            header: labelForJsonlSampleColumnKey(fieldKey),
            enableSorting: false,
            enableColumnFilter: false,
            size: 200,
            minSize: 96,
            cell: ({ getValue }) => (
              <div className="file-sampling-cell max-h-24 min-w-0 max-w-full overflow-y-auto py-0.5">
                <Text
                  kind="body/regular/sm"
                  className="whitespace-pre-wrap wrap-break-word font-mono text-left"
                >
                  {formatJsonlSampleCellValue(getValue())}
                </Text>
              </div>
            ),
          });
        }),
      ];
    };
  }, [columnKeys]);

  const studioDataViewAttributes = useMemo(() => {
    const user = attributes?.studioDataView ?? {};
    const { className: tableShellClassName, ...tablePassthrough } = attributes?.table ?? {};
    const internalTableContent = {
      stickyTableHeader: true,
      className:
        'file-sampling-snippet-table min-h-0 flex-1 [&_tbody_td]:align-top [&_tbody_tr]:align-top',
      renderEmptyState: () => (
        <TableEmptyState
          className="py-8"
          header="No sample rows"
          emptyMessage="Adjust sampling or pick another file. Each line should be a JSON object for column headers."
        />
      ),
    };

    return {
      ...user,
      DataViewRoot: {
        ...tablePassthrough,
        ...user.DataViewRoot,
        data: tableRows,
        totalCount: tableRows.length,
        className: classnames(
          DEFAULT_TABLE_SHELL,
          tableShellClassName,
          user.DataViewRoot?.className
        ),
      },
      DataViewTableContent: {
        ...internalTableContent,
        ...user.DataViewTableContent,
        className: classnames(internalTableContent.className, user.DataViewTableContent?.className),
      },
    };
  }, [attributes?.studioDataView, attributes?.table, tableRows]);

  useEffect(() => {
    if (!enabled) {
      onSampledContentChange('');
      return;
    }
    if (isFileContentError) {
      onSampledContentChange('');
      return;
    }
    if (fileContent === undefined) {
      return;
    }
    onSampledContentChange(sampledText);
  }, [enabled, isFileContentError, fileContent, sampledText, onSampledContentChange]);

  const editorAttrs = attributes?.editor ?? {};
  const isLoadingSample = enabled && isLoadingFileContent;

  const sampleShellClassName =
    displayMode === 'code'
      ? classnames(DEFAULT_EDITOR_CLASS, editorAttrs.className)
      : classnames(DEFAULT_TABLE_SHELL, attributes?.table?.className);

  if (isFileContentError) {
    return (
      <Banner kind="inline" status="error">
        Failed to load file content. Please select a different file.
      </Banner>
    );
  }

  return (
    <Stack gap="4">
      {isLoadingSample ? (
        <Flex align="center" justify="center" className={sampleShellClassName}>
          <Spinner description="Loading file..." />
        </Flex>
      ) : displayMode === 'code' ? (
        <CodeEditor
          content={sampledText}
          contentType={ContentType.JSONL}
          hideCopyButton
          {...editorAttrs}
          className={classnames(DEFAULT_EDITOR_CLASS, editorAttrs.className)}
        />
      ) : (
        <StudioDataView<JsonlObjectSampleRow>
          dataViewState={dataViewState}
          makeColumns={makeColumns}
          maxTwoLines={false}
          attributes={studioDataViewAttributes}
        />
      )}

      {slotFooter}
    </Stack>
  );
};
