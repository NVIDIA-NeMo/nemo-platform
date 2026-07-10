// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, PageHeader, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { AddColumnPalette } from '@studio/components/AddColumnPalette';
import type { AddColumnSelection } from '@studio/components/AddColumnPalette/types';
import { ColumnConfigPanel } from '@studio/components/ColumnConfigPanel';
import { findTemplate } from '@studio/components/CreateFilesetStart/templates';
import { DagCanvas } from '@studio/components/DagCanvas';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  type BuilderColumn,
  buildColumnsFromTemplate,
  buildGraph,
  defaultColumnName,
  findColumnOption,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';
import { getDataDesignerJobListRoute, getNewDataDesignerJobRoute } from '@studio/routes/utils';
import { type FC, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * The "Build from scratch" column builder. Composes the {@link AddColumnPalette} (left),
 * the {@link DagCanvas} recipe graph (center), and a {@link ColumnConfigPanel} that opens
 * on the right when a column is added or a node is clicked — so the canvas stays visible
 * while the column is configured.
 *
 * Edges are derived from the entered values: a column that references another via a
 * Jinja2 `{{ column_name }}` token (or a column-name field) gets an edge from the
 * referenced column, so the graph reflects real data dependencies rather than add order.
 */
export const DataDesignerJobBuildRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const [searchParams] = useSearchParams();

  // A `?template=<id>` param (set by the "Start from a template" flow) preloads the
  // canvas with that recipe's columns; without it, the canvas starts empty ("scratch").
  const template = useMemo(() => {
    const templateId = searchParams.get('template');
    return templateId ? (findTemplate(templateId) ?? null) : null;
  }, [searchParams]);

  const heading = template ? template.title : 'Build from scratch';

  useBreadcrumbs({
    items: [
      { href: getDataDesignerJobListRoute(workspace), slotLabel: 'Data Designer' },
      { href: getNewDataDesignerJobRoute(workspace), slotLabel: 'New fileset' },
      { slotLabel: heading },
    ],
  });

  // Seed once from the template (if any). `useState` initializer runs a single time, so
  // navigating with a template preloads its columns without re-seeding on every render.
  const [columns, setColumns] = useState<BuilderColumn[]>(() =>
    template ? buildColumnsFromTemplate(template.columns) : []
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Set only when a column is added, so the canvas centers new nodes but not clicked ones.
  const [focusId, setFocusId] = useState<string | null>(null);
  // Continue numbering after any preloaded template columns so ids stay unique.
  const nextId = useRef(columns.length);

  const selectedColumn = columns.find((column) => column.id === selectedId) ?? null;

  const takenNames = useMemo(
    () =>
      new Set(columns.filter((column) => column.id !== selectedId).map((column) => column.name)),
    [columns, selectedId]
  );

  const { nodes, edges } = useMemo(() => buildGraph(columns), [columns]);

  const handleAddColumn = (selection: AddColumnSelection) => {
    const option = findColumnOption(selection);
    if (!option) return;
    const id = `col-${nextId.current++}`;
    setColumns((prev) => {
      const name = defaultColumnName(option, new Set(prev.map((column) => column.name)));
      return [...prev, { id, option, name, values: {} }];
    });
    setSelectedId(id);
    setFocusId(id);
  };

  const patchColumn = (id: string, patch: { name?: string; values?: Record<string, string> }) =>
    setColumns((prev) =>
      prev.map((column) => (column.id === id ? { ...column, ...patch } : column))
    );

  const removeColumn = (id: string) => {
    setColumns((prev) => prev.filter((column) => column.id !== id));
    setSelectedId((current) => (current === id ? null : current));
  };

  return (
    <AccessibleTitle title={heading}>
      <div className="flex h-full flex-col">
        <div className="shrink-0 px-density-2xl pt-density-2xl pb-density-xl">
          <PageHeader
            slotHeading={heading}
            slotDescription={
              template
                ? `${template.description} Adjust any column, wire in more, then run.`
                : 'Open an empty canvas and add columns block by block, your way.'
            }
          />
        </div>

        <div className="flex min-h-0 flex-1 border-t border-base">
          <aside className="w-[240px] shrink-0 border-r border-base p-density-lg">
            <AddColumnPalette onAddColumn={handleAddColumn} />
          </aside>

          <div className="relative min-w-0 flex-1">
            {columns.length === 0 ? (
              <Flex align="center" justify="center" className="h-full">
                <Text kind="body/regular/md" className="text-secondary">
                  Empty canvas — add a column from the left to get started.
                </Text>
              </Flex>
            ) : (
              <DagCanvas
                nodes={nodes}
                edges={edges}
                onNodeClick={setSelectedId}
                onNodeDelete={removeColumn}
                focusNodeId={focusId}
              />
            )}
          </div>

          <div className="w-[240px] shrink-0 border-l border-base bg-surface-base">
            {selectedColumn ? (
              <ColumnConfigPanel
                column={selectedColumn}
                takenNames={takenNames}
                onChange={(patch) => patchColumn(selectedColumn.id, patch)}
                onRemove={() => removeColumn(selectedColumn.id)}
                onClose={() => setSelectedId(null)}
              />
            ) : (
              <Flex align="center" justify="center" className="h-full p-density-lg">
                <Text kind="body/regular/sm" className="text-secondary text-center">
                  Select a column to configure it, or add one from the left.
                </Text>
              </Flex>
            )}
          </div>
        </div>
      </div>
    </AccessibleTitle>
  );
};
