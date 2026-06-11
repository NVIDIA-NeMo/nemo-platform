// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { splitMessageWithLabels } from '@nemo/common/src/components/Chat/MessageContent/utils';
import { CodeDisplay } from '@nemo/common/src/components/CodeDisplay';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { simpleHash } from '@nemo/common/src/utils/simpleHash';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { childrenToText } from '@nvidia/foundations-react-core/lib';
import cn from 'classnames';
import { decode } from 'html-entities';
import {
  Children,
  type FC,
  isValidElement,
  type MouseEvent,
  type PropsWithChildren,
  type ReactElement,
  type ReactNode,
  useCallback,
  useMemo,
  useState,
} from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

export interface MarkdownTableOptions {
  expandableCells?: boolean;
}

export interface MessageContentProps {
  content?: string | null;
  markdownLinkComponent?: Components['a'];
  markdownTableOptions?: MarkdownTableOptions;
  renderAsMarkdown?: boolean;
}

const INLINE_CODE_CLASS = 'rounded bg-gray-050 px-1 py-0.5 font-sans text-sm dark:bg-gray-800';

interface MarkdownTableColumn {
  id: string;
  header: ReactNode;
}

interface MarkdownTableRow {
  id: string;
  cells: readonly ReactNode[];
  cellValues: readonly string[];
  expandedRowIds?: ReadonlySet<string>;
}

interface ElementWithChildrenProps {
  children?: ReactNode;
}

interface MarkdownAstNode {
  children?: MarkdownAstNode[];
  ordered?: boolean | null;
  spread?: boolean;
  start?: number | null;
  type: string;
  value?: unknown;
}

interface MarkdownAstParent extends MarkdownAstNode {
  children: MarkdownAstNode[];
}

interface MarkdownAstListNode extends MarkdownAstParent {
  ordered?: boolean | null;
  start?: number | null;
  type: 'list';
}

interface MarkdownAstListItemNode extends MarkdownAstParent {
  spread?: boolean;
  type: 'listItem';
}

interface MarkdownTableData {
  columns: readonly MarkdownTableColumn[];
  rows: readonly MarkdownTableRow[];
}

const MarkdownParagraph: FC<PropsWithChildren> = ({ children }) => (
  <Text asChild kind="body/regular/md">
    <p className="mb-density-xl text-sm leading-[160%] last:mb-0">{children}</p>
  </Text>
);

interface MarkdownDataViewTableProps extends PropsWithChildren {
  options?: MarkdownTableOptions;
}

interface MarkdownTableCellProps {
  children: ReactNode;
  expanded: boolean;
  expandable: boolean;
  onToggle: () => void;
}

const DEFAULT_MARKDOWN_TABLE_OPTIONS: Required<MarkdownTableOptions> = {
  expandableCells: true,
};

const isElementWithChildren = (node: ReactNode): node is ReactElement<ElementWithChildrenProps> =>
  isValidElement<ElementWithChildrenProps>(node);

const isElementNamed = (
  node: ReactNode,
  elementName: 'thead' | 'tbody' | 'tr' | 'th' | 'td' | 'p'
): node is ReactElement<ElementWithChildrenProps> =>
  isElementWithChildren(node) && node.type === elementName;

const getChildNodes = (node: ReactElement<ElementWithChildrenProps>): ReactNode[] =>
  Children.toArray(node.props.children);

const isWhitespaceTextNode = (node: ReactNode): node is string =>
  typeof node === 'string' && node.trim().length === 0;

const isMarkdownParagraphElement = (
  node: ReactNode
): node is ReactElement<ElementWithChildrenProps> =>
  isElementWithChildren(node) && (node.type === MarkdownParagraph || isElementNamed(node, 'p'));

const renderListItemChildren = (children: ReactNode): ReactNode => {
  const childNodes = Children.toArray(children);
  const firstContentIndex = childNodes.findIndex((child) => !isWhitespaceTextNode(child));
  const firstContent = childNodes[firstContentIndex];

  if (firstContentIndex === -1 || !isMarkdownParagraphElement(firstContent)) {
    return children;
  }

  return [
    <Text asChild kind="body/regular/md" key="leading-list-paragraph">
      <span className="text-sm leading-[160%]">{getChildNodes(firstContent)}</span>
    </Text>,
    ...childNodes.slice(firstContentIndex + 1),
  ];
};

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

const isMarkdownAstNode = (value: unknown): value is MarkdownAstNode =>
  typeof value === 'object' &&
  value !== null &&
  typeof (value as { type?: unknown }).type === 'string';

const hasMarkdownAstChildren = (node: MarkdownAstNode): node is MarkdownAstParent =>
  Array.isArray(node.children);

const isMarkdownAstList = (node: MarkdownAstNode): node is MarkdownAstListNode =>
  node.type === 'list' && hasMarkdownAstChildren(node);

const isMarkdownAstListItem = (node: MarkdownAstNode): node is MarkdownAstListItemNode =>
  node.type === 'listItem' && hasMarkdownAstChildren(node);

const isMarkdownAstParagraph = (node: MarkdownAstNode): boolean => node.type === 'paragraph';

const getMarkdownAstText = (node: MarkdownAstNode): string => {
  if (typeof node.value === 'string') return node.value;
  if (!hasMarkdownAstChildren(node)) return '';
  return node.children.map(getMarkdownAstText).join('');
};

const isEmptyMarkdownAstListItem = (
  node: MarkdownAstNode | undefined
): node is MarkdownAstListItemNode =>
  isMarkdownAstNode(node) &&
  isMarkdownAstListItem(node) &&
  (node.children.length === 0 ||
    node.children.every(
      (child) => isMarkdownAstParagraph(child) && !getMarkdownAstText(child).trim()
    ));

const getMarkdownListStart = (node: MarkdownAstListNode): number => node.start ?? 1;

const shouldMergeOrderedLists = (
  currentNode: MarkdownAstNode,
  nextNode: MarkdownAstNode | undefined
): nextNode is MarkdownAstListNode => {
  if (!isMarkdownAstList(currentNode) || !currentNode.ordered) return false;
  if (!nextNode || !isMarkdownAstList(nextNode) || !nextNode.ordered) return false;

  return (
    getMarkdownListStart(nextNode) ===
    getMarkdownListStart(currentNode) + currentNode.children.length
  );
};

const mergeAdjacentOrderedLists = (children: MarkdownAstNode[], index: number): void => {
  const currentNode = children[index];
  if (!currentNode || !isMarkdownAstList(currentNode)) return;

  while (true) {
    const nextNode = children[index + 1];
    if (!shouldMergeOrderedLists(currentNode, nextNode)) break;

    currentNode.children.push(...nextNode.children);
    children.splice(index + 1, 1);
  }
};

const mergeEmptyOrderedListMarker = (children: MarkdownAstNode[], index: number): void => {
  const currentNode = children[index];
  const nextNode = children[index + 1];
  if (!currentNode || !nextNode || !isMarkdownAstList(currentNode) || !currentNode.ordered) return;
  if (currentNode.children.length !== 1 || !isEmptyMarkdownAstListItem(currentNode.children[0])) {
    return;
  }
  if (!isMarkdownAstParagraph(nextNode)) return;

  const listItem = currentNode.children[0];
  listItem.children = [nextNode];
  listItem.spread = false;
  currentNode.spread = false;

  const followingNode = children[index + 2];
  const shouldNestFollowingUnorderedList =
    followingNode !== undefined &&
    isMarkdownAstList(followingNode) &&
    followingNode.ordered !== true;

  if (shouldNestFollowingUnorderedList) {
    listItem.children.push(followingNode);
    children.splice(index + 1, 2);
    return;
  }

  children.splice(index + 1, 1);
};

const normalizeMarkdownAstLists = (parent: MarkdownAstParent): void => {
  for (let index = 0; index < parent.children.length; index++) {
    mergeEmptyOrderedListMarker(parent.children, index);
  }

  for (let index = 0; index < parent.children.length; index++) {
    mergeAdjacentOrderedLists(parent.children, index);
  }

  for (let index = 0; index < parent.children.length; index++) {
    const child = parent.children[index];
    if (child && hasMarkdownAstChildren(child)) normalizeMarkdownAstLists(child);
  }
};

const remarkNormalizeEmptyOrderedListMarkers =
  () =>
  (tree: unknown): void => {
    if (!isMarkdownAstNode(tree) || !hasMarkdownAstChildren(tree)) return;
    normalizeMarkdownAstLists(tree);
  };

const getMarkdownTableOptions = (
  options: MarkdownTableOptions | undefined
): Required<MarkdownTableOptions> => ({
  ...DEFAULT_MARKDOWN_TABLE_OPTIONS,
  ...options,
});

const MarkdownTableCell = ({
  children,
  expanded,
  expandable,
  onToggle,
}: MarkdownTableCellProps) => {
  if (!expandable) {
    return <span className="block whitespace-normal break-words">{children}</span>;
  }

  const text = getNodeText(children);

  return (
    <button
      aria-label={text || undefined}
      aria-expanded={expanded}
      className="block w-full min-w-0 max-w-full cursor-pointer appearance-none overflow-hidden border-0 bg-transparent p-0 text-left font-inherit text-inherit"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      type="button"
    >
      <span
        className={`min-w-0 max-w-full whitespace-normal break-words [&_span]:whitespace-normal ${
          expanded ? 'block' : 'line-clamp-2'
        }`}
        data-collapsed={!expanded || undefined}
      >
        {children}
      </span>
    </button>
  );
};

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

const MarkdownDataViewTable: FC<MarkdownDataViewTableProps> = ({ children, options }) => {
  const tableOptions = useMemo(() => getMarkdownTableOptions(options), [options]);
  const { columns, rows } = useMemo(() => parseMarkdownTable(children), [children]);
  const dataViewState = DataView.useDataViewState();
  const [expandedRowIds, setExpandedRowIds] = useState<ReadonlySet<string>>(() => new Set());
  const data = useMemo(
    () => rows.map((row) => ({ ...row, expandedRowIds })),
    [expandedRowIds, rows]
  );
  const toggleExpandedRow = useCallback((rowId: string) => {
    setExpandedRowIds((current) => {
      const next = new Set(current);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  }, []);
  const handleTableClick = useCallback(
    (event: MouseEvent<HTMLTableElement>) => {
      if (!tableOptions.expandableCells || !(event.target instanceof Element)) return;

      const rowElement = event.target.closest('tbody tr[data-row-id]');
      const rowId = rowElement?.getAttribute('data-row-id');
      if (!rowId) return;

      toggleExpandedRow(rowId);
    },
    [tableOptions.expandableCells, toggleExpandedRow]
  );
  const makeColumns = useMemo<DataView.MakeColumns<MarkdownTableRow>>(
    () => (columnHelper) =>
      columns.map((column, columnIndex) =>
        columnHelper.accessor((row) => row.cellValues[columnIndex] ?? '', {
          id: column.id,
          header: () => column.header,
          cell: ({ row }) => {
            return (
              <MarkdownTableCell
                expanded={row.original.expandedRowIds?.has(row.original.id) ?? false}
                expandable={tableOptions.expandableCells}
                onToggle={() => toggleExpandedRow(row.original.id)}
              >
                {row.original.cells[columnIndex] ?? ''}
              </MarkdownTableCell>
            );
          },
          enableResizing: false,
          enableSorting: true,
        })
      ),
    [columns, tableOptions, toggleExpandedRow]
  );

  if (!columns.length) return null;

  return (
    <DataView.Root
      autoCellTooltips={false}
      className="my-density-md min-w-0 max-w-full overflow-hidden [&>div]:min-h-0"
      data={data}
      dataMode="sort-filter-only"
      makeColumns={makeColumns}
      state={dataViewState}
      totalCount={rows.length}
    >
      <DataView.Toolbar>
        <DataView.SearchBar debounce={0} placeholder="Search table" />
      </DataView.Toolbar>
      <DataView.TableContent
        className={`min-h-0 border-0 [&_.nv-table-head]:border-b-0 [&_.nv-table-row]:border-b-0 [&_thead_th>.data-view-header-control]:!max-w-none [&_.data-view-header-control>span]:!overflow-visible [&_.data-view-header-control>span]:!text-clip ${tableOptions.expandableCells ? '[&_tbody_tr]:cursor-pointer' : ''}`}
        density="compact"
        layout="auto"
        onClick={handleTableClick}
        stickyTableHeader={false}
      />
    </DataView.Root>
  );
};

const messageMarkdownComponents: Components = {
  h1: ({ children }) => (
    <Text asChild kind="title/lg">
      <h1 className="mb-density-sm mt-density-3xl first:mt-0">{children}</h1>
    </Text>
  ),
  h2: ({ children }) => (
    <Text asChild kind="title/md">
      <h2 className="mb-density-sm mt-density-3xl first:mt-0">{children}</h2>
    </Text>
  ),
  h3: ({ children }) => (
    <Text asChild kind="label/bold/md">
      <h3 className="mb-density-sm mt-density-2xl first:mt-0">{children}</h3>
    </Text>
  ),
  h4: ({ children }) => (
    <Text asChild kind="label/bold/sm">
      <h4 className="mb-density-sm mt-density-md first:mt-0">{children}</h4>
    </Text>
  ),
  h5: ({ children }) => (
    <Text asChild kind="label/bold/sm">
      <h5 className="mb-density-sm mt-density-md first:mt-0">{children}</h5>
    </Text>
  ),
  h6: ({ children }) => (
    <Text asChild kind="label/bold/sm">
      <h6 className="mb-density-sm mt-density-md first:mt-0">{children}</h6>
    </Text>
  ),
  p: MarkdownParagraph,
  ul: ({ children, className }) => (
    <ul className={cn('my-density-xl list-disc pl-density-lg', className)}>{children}</ul>
  ),
  ol: ({ children, className, start }) => (
    <ol className={cn('my-density-xl list-decimal pl-density-2xl', className)} start={start}>
      {children}
    </ol>
  ),
  li: ({ children, className }) => (
    <li
      className={cn(
        'mb-density-sm whitespace-normal pl-density-xs text-sm leading-[160%] last:mb-0 [&>p]:my-0',
        className
      )}
    >
      {renderListItemChildren(children)}
    </li>
  ),
  hr: () => <hr className="my-density-sm border-base" />,
  blockquote: ({ children, className }) => (
    <blockquote
      className={cn('my-density-xs border-l-4 border-base pl-density-sm text-secondary', className)}
    >
      {children}
    </blockquote>
  ),
  img: ({ src, alt }) => <img src={src} alt={alt ?? ''} className="max-w-full" />,
  // Most chat surfaces keep model-supplied links inert. Consumers that know how
  // to handle links can provide their own renderer.
  a: ({ children }) => <span>{children}</span>,
  code: ({ children }) => <code className={INLINE_CODE_CLASS}>{children}</code>,
  table: ({ children }) => <MarkdownDataViewTable>{children}</MarkdownDataViewTable>,
};

/**
 * This component takes a content string from a chat response and converts into a user readable
 * list of snippets using content-specific render types. Currently supports plaintext and code.
 */
export const MessageContent: FC<PropsWithChildren<MessageContentProps>> = ({
  content,
  markdownLinkComponent,
  markdownTableOptions,
  renderAsMarkdown = true,
}) => {
  const snippets = useMemo(() => splitMessageWithLabels(content), [content]);
  const markdownComponents = useMemo<Components>(
    () => ({
      ...messageMarkdownComponents,
      a: markdownLinkComponent ?? messageMarkdownComponents.a,
      table: ({ children }) => (
        <MarkdownDataViewTable options={markdownTableOptions}>{children}</MarkdownDataViewTable>
      ),
    }),
    [markdownLinkComponent, markdownTableOptions]
  );

  return snippets.map((descriptor) => {
    const contentHash = simpleHash(descriptor.value);
    if (descriptor.type === 'plaintext') {
      return (
        <div
          className="whitespace-normal text-sm font-normal leading-[160%]"
          data-testid="chat-message-content-text"
          key={`plaintext-${contentHash}`}
        >
          {renderAsMarkdown ? (
            <Markdown
              remarkPlugins={[remarkGfm, remarkNormalizeEmptyOrderedListMarkers]}
              components={markdownComponents}
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
