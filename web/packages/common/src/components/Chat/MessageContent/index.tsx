// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { splitMessageWithLabels } from '@nemo/common/src/components/Chat/MessageContent/utils';
import { CodeDisplay } from '@nemo/common/src/components/CodeDisplay';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { simpleHash } from '@nemo/common/src/utils/simpleHash';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { childrenToText } from '@nvidia/foundations-react-core/lib';
import { decode } from 'html-entities';
import {
  Children,
  type FC,
  isValidElement,
  type PropsWithChildren,
  type ReactElement,
  type ReactNode,
  useMemo,
} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export interface MessageContentProps {
  content?: string | null;
  renderAsMarkdown?: boolean;
}

interface MarkdownTableColumn {
  id: string;
  header: ReactNode;
  headerText: string;
}

interface MarkdownTableRow {
  id: string;
  cells: readonly ReactNode[];
  cellValues: readonly string[];
}

interface ElementWithChildrenProps {
  children?: ReactNode;
}

interface MarkdownTableData {
  columns: readonly MarkdownTableColumn[];
  rows: readonly MarkdownTableRow[];
}

const isElementWithChildren = (node: ReactNode): node is ReactElement<ElementWithChildrenProps> =>
  isValidElement<ElementWithChildrenProps>(node);

const isElementNamed = (
  node: ReactNode,
  elementName: 'thead' | 'tbody' | 'tr' | 'th' | 'td'
): node is ReactElement<ElementWithChildrenProps> =>
  isElementWithChildren(node) && node.type === elementName;

const getChildNodes = (node: ReactElement<ElementWithChildrenProps>): ReactNode[] =>
  Children.toArray(node.props.children);

const getRowCells = (row: ReactElement<ElementWithChildrenProps>): readonly ReactNode[] =>
  getChildNodes(row)
    .filter((cell) => isElementNamed(cell, 'th') || isElementNamed(cell, 'td'))
    .map((cell) => cell.props.children ?? '');

const getSectionRows = (
  section: ReactElement<ElementWithChildrenProps> | undefined
): readonly (readonly ReactNode[])[] => {
  if (!section) return [];

  return getChildNodes(section)
    .filter((child) => isElementNamed(child, 'tr'))
    .map(getRowCells);
};

const getNodeText = (node: ReactNode): string => childrenToText(node).trim();

const parseMarkdownTable = (children: ReactNode): MarkdownTableData => {
  const tableChildren = Children.toArray(children);
  const head = tableChildren.find((child) => isElementNamed(child, 'thead'));
  const bodies = tableChildren.filter((child) => isElementNamed(child, 'tbody'));
  const headerRows = getSectionRows(head);
  const bodyRows = bodies.flatMap(getSectionRows);
  const headerCells = headerRows[0] ?? bodyRows[0] ?? [];
  const dataRows = headerRows.length > 0 ? bodyRows : bodyRows.slice(1);
  const columnCount = Math.max(headerCells.length, ...dataRows.map((row) => row.length));

  return {
    columns: Array.from({ length: columnCount }, (_, index) => ({
      id: `column-${index}`,
      header: headerCells[index] ?? `Column ${index + 1}`,
      headerText: getNodeText(headerCells[index] ?? `Column ${index + 1}`),
    })),
    rows: dataRows.map((cells, rowIndex) => ({
      id: `row-${rowIndex}`,
      cells: Array.from({ length: columnCount }, (_, cellIndex) => cells[cellIndex] ?? ''),
      cellValues: Array.from({ length: columnCount }, (_, cellIndex) =>
        getNodeText(cells[cellIndex] ?? '')
      ),
    })),
  };
};

const MarkdownDataViewTable: FC<PropsWithChildren> = ({ children }) => {
  const { columns, rows } = useMemo(() => parseMarkdownTable(children), [children]);
  const dataViewState = DataView.useDataViewState();
  const makeColumns = useMemo<DataView.MakeColumns<MarkdownTableRow>>(
    () => (columnHelper) =>
      columns.map((column, columnIndex) =>
        columnHelper.accessor((row) => row.cellValues[columnIndex] ?? '', {
          id: column.id,
          header: () => column.header,
          cell: ({ row }) => row.original.cells[columnIndex] ?? '',
          enableResizing: false,
          enableSorting: true,
        })
      ),
    [columns]
  );

  if (!columns.length) return null;

  return (
    <DataView.Root
      autoCellTooltips={false}
      className="my-density-md min-w-0 max-w-full overflow-hidden [&>div]:min-h-0"
      data={[...rows]}
      dataMode="sort-filter-only"
      makeColumns={makeColumns}
      state={dataViewState}
      totalCount={rows.length}
    >
      <DataView.Toolbar>
        <DataView.SearchBar debounce={0} placeholder="Search table" />
      </DataView.Toolbar>
      <DataView.TableContent
        className="min-h-0 border-0 [&_.nv-table-head]:border-b-0 [&_.nv-table-row]:border-b-0"
        density="compact"
        layout="auto"
        stickyTableHeader={false}
      />
    </DataView.Root>
  );
};

/**
 * This component takes a content string from a chat response and converts into a user readable
 * list of snippets using content-specific render types. Currently supports plaintext and code.
 */
export const MessageContent: FC<PropsWithChildren<MessageContentProps>> = ({
  content,
  renderAsMarkdown = true,
}) => {
  const snippets = useMemo(() => splitMessageWithLabels(content), [content]);
  return snippets.map((descriptor) => {
    const contentHash = simpleHash(descriptor.value);
    if (descriptor.type === 'plaintext') {
      return (
        <div
          className="text-base font-normal leading-[150%] text-sm"
          data-testid="chat-message-content-text"
          key={`plaintext-${contentHash}`}
        >
          {renderAsMarkdown ? (
            <Markdown
              remarkPlugins={[remarkGfm]}
              components={{
                // We don't want links embedded in markdown responses to be clickable
                a: ({ ...props }) => <span>{props.children}</span>,
                table: ({ children }) => <MarkdownDataViewTable>{children}</MarkdownDataViewTable>,
              }}
            >
              {decode(descriptor.value)}
            </Markdown>
          ) : (
            <Text kind="mono/md" className="whitespace-pre-wrap">
              {decode(descriptor.value)}
            </Text>
          )}
        </div>
      );
    } else if (descriptor.type === 'code') {
      return (
        <Stack key={`code-${contentHash}`}>
          {renderAsMarkdown ? (
            <CodeDisplay data-testid="chat-message-content-text">{descriptor.value}</CodeDisplay>
          ) : (
            <Text kind="mono/md" className="whitespace-pre-wrap">
              {descriptor.value}
            </Text>
          )}
        </Stack>
      );
    }
  });
};
