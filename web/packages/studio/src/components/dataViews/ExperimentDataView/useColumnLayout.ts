// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getGetExperimentQueryKey, useUpdateExperiment } from '@nemo/sdk/generated/platform/api';
import type { ColumnLayout, ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { useQueryClient } from '@tanstack/react-query';

/**
 * Columns hidden until someone says otherwise. Applied only when the experiment has no saved layout
 * at all — once a layout exists it is authoritative, so a deliberate "show everything" is not
 * quietly re-hidden on the next load.
 */
const DEFAULT_HIDDEN_COLUMNS: readonly string[] = ['created_by', 'updated_at'];

/**
 * The table's `columnVisibility` only records columns someone has toggled; anything absent is
 * visible. Inverting it back to a plain id list is what makes the saved layout comparable to the
 * live one, and keeps what we persist independent of how many columns happen to exist.
 */
export const hiddenColumnIds = (visibility: Record<string, boolean>): string[] =>
  Object.entries(visibility)
    .filter(([, isVisible]) => !isVisible)
    .map(([id]) => id)
    .sort();

const toVisibility = (hidden: readonly string[]): Record<string, boolean> =>
  Object.fromEntries(hidden.map((id) => [id, false]));

/** Order is a sequence, so it compares element-wise; hidden is a set, so it compares sorted. */
const sameSequence = (a: readonly string[], b: readonly string[]): boolean =>
  a.length === b.length && a.every((value, index) => value === b[index]);

const sameSet = (a: readonly string[], b: readonly string[]): boolean =>
  sameSequence([...a].sort(), [...b].sort());

/** The hidden ids a layout implies, falling back to the built-in defaults only when none is saved. */
const savedHiddenColumns = (layout: ColumnLayout | undefined): readonly string[] =>
  layout ? (layout.hidden ?? []) : DEFAULT_HIDDEN_COLUMNS;

/**
 * Seed values for the data view's column state, so the table opens on the experiment's saved layout
 * instead of flashing the default one and re-arranging once the group loads.
 */
export const seedColumnState = (
  layout: ColumnLayout | undefined
): { columnOrder: string[]; columnVisibility: Record<string, boolean> } => ({
  columnOrder: [...(layout?.order ?? [])],
  columnVisibility: toVisibility(savedHiddenColumns(layout)),
});

/**
 * Whether the live column state differs from the saved layout — which is the whole condition for
 * offering a save. An untouched table sitting on its saved layout must read as clean, including the
 * case where nothing has ever been saved and the table is on its defaults.
 */
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
 * Tracks the evaluations table's column layout against the copy saved on the experiment, and
 * persists it on request.
 *
 * The layout lives on the experiment rather than in browser storage because it describes the
 * experiment — which of its evaluators are worth a column, and in what order they read — so it
 * should follow the experiment between browsers and between people looking at the same results.
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
    // PUT replaces the whole experiment, and the fields below are written unconditionally by the
    // API — so they are echoed back as-is. `pareto` and the display flags are guarded server-side by
    // whether the client sent them, so omitting them preserves what is already saved.
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
