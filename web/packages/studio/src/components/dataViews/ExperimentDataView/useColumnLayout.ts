// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getGetExperimentQueryKey, useUpdateExperiment } from '@nemo/sdk/generated/platform/api';
import type { ColumnLayout, ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { useQueryClient } from '@tanstack/react-query';

/** Applied only when no layout is saved; a saved layout is authoritative, including an empty one. */
const DEFAULT_HIDDEN_COLUMNS: readonly string[] = ['created_by', 'updated_at'];

/** `columnVisibility` only records toggled columns; anything absent is visible. */
export const hiddenColumnIds = (visibility: Record<string, boolean>): string[] =>
  Object.entries(visibility)
    .filter(([, isVisible]) => !isVisible)
    .map(([id]) => id)
    .sort();

const toVisibility = (hidden: readonly string[]): Record<string, boolean> =>
  Object.fromEntries(hidden.map((id) => [id, false]));

const sameSequence = (a: readonly string[], b: readonly string[]): boolean =>
  a.length === b.length && a.every((value, index) => value === b[index]);

const sameSet = (a: readonly string[], b: readonly string[]): boolean =>
  sameSequence([...a].sort(), [...b].sort());

const savedHiddenColumns = (layout: ColumnLayout | undefined): readonly string[] =>
  layout ? (layout.hidden ?? []) : DEFAULT_HIDDEN_COLUMNS;

export const seedColumnState = (
  layout: ColumnLayout | undefined
): { columnOrder: string[]; columnVisibility: Record<string, boolean> } => ({
  columnOrder: [...(layout?.order ?? [])],
  columnVisibility: toVisibility(savedHiddenColumns(layout)),
});

export const isLayoutDirty = ({
  saved,
  columnOrder,
  columnVisibility,
}: {
  saved: ColumnLayout | undefined;
  columnOrder: string[];
  columnVisibility: Record<string, boolean>;
}): boolean =>
  !sameSequence(columnOrder, saved?.order ?? []) ||
  !sameSet(hiddenColumnIds(columnVisibility), savedHiddenColumns(saved));

export interface ExperimentColumnLayout {
  /** True when the live column order or visibility differs from what is saved on the experiment. */
  hasUnsavedLayout: boolean;
  /** Persists the live layout onto the experiment. */
  save: () => void;
  isSaving: boolean;
}

/**
 * Tracks the evaluations table's column layout against the copy saved on the experiment.
 *
 * The layout lives on the experiment, not in browser storage, so it follows the experiment between
 * browsers and between people looking at the same results.
 */
export function useColumnLayout({
  workspace,
  group,
  columnOrder,
  columnVisibility,
}: {
  workspace: string;
  group: ExperimentResponse;
  columnOrder: string[];
  columnVisibility: Record<string, boolean>;
}): ExperimentColumnLayout {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { mutate: saveGroup, isPending: isSaving } = useUpdateExperiment({
    mutation: {
      onSuccess: () => {
        toast.success('Saved the column layout for this experiment.');
        queryClient.invalidateQueries({
          queryKey: getGetExperimentQueryKey(workspace, group.name),
        });
      },
      onError: () => toast.error('Failed to save the column layout.'),
    },
  });

  const currentHidden = hiddenColumnIds(columnVisibility);
  const hasUnsavedLayout = isLayoutDirty({
    saved: group.column_layout,
    columnOrder,
    columnVisibility,
  });

  const save = () => {
    // PUT replaces the whole experiment: the fields below are written unconditionally by the API and
    // must be echoed back, while omitted ones (`pareto`, the display flags) are preserved server-side.
    saveGroup({
      workspace,
      name: group.name,
      data: {
        name: group.name,
        description: group.description,
        insight_id: group.insight_id,
        summary: group.summary,
        metadata: group.metadata,
        default_sort: group.default_sort,
        column_layout: { order: columnOrder, hidden: currentHidden },
      },
    });
  };

  return { hasUnsavedLayout, save, isSaving };
}
