// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import type { AddColumnSelection } from '@studio/components/AddColumnPalette/types';
import type { FilesetTemplate } from '@studio/components/CreateFilesetStart/types';
import {
  type BuilderColumn,
  buildColumnsFromTemplate,
  buildGraph,
  defaultColumnName,
  findColumnOption,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';
import {
  type BuilderModel,
  type BuilderModelPatch,
  buildModelsFromTemplate,
  builderModelFromSelection,
  resolveTemplateModel,
} from '@studio/routes/DataDesignerJobBuildRoute/models';
import { useEffect, useMemo, useRef, useState } from 'react';

/** Which palette the left aside shows. */
export type PaletteTab = 'columns' | 'models';

/**
 * Column/model state for the recipe builder. Selecting a column and selecting a model are
 * mutually exclusive — only one config panel shows at a time.
 *
 * Job-level concerns (name, row count, validation, preview, submit) live in the route so
 * this hook stays a pure graph-editing store.
 *
 * `modelGroups` auto-fills a template's seeded models once the platform model list loads.
 * `modelsSettled` gates that auto-fill on the full (all-pages) model list being available.
 */
export const useJobBuilder = (
  template: FilesetTemplate | null,
  modelGroups: ModelWorkspaceGroup[],
  modelsSettled: boolean
) => {
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

  // The models referenced by LLM columns via `model_alias`; part of the same job config.
  // Seeded once from the template (if any); providers/models are auto-filled below.
  const [models, setModels] = useState<BuilderModel[]>(() =>
    buildModelsFromTemplate(template?.models)
  );
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const nextModelId = useRef(models.length);
  const [paletteTab, setPaletteTab] = useState<PaletteTab>('columns');

  const autoFilled = useRef(false);
  useEffect(() => {
    if (autoFilled.current || !modelsSettled || modelGroups.length === 0) return;
    autoFilled.current = true;
    setModels((prev) => {
      let changed = false;
      const next = prev.map((model) => {
        if (model.provider) return model;
        const resolved = resolveTemplateModel(modelGroups, model.model || undefined);
        changed = true;
        return resolved ? { ...model, ...resolved } : { ...model, model: '' };
      });
      return changed ? next : prev;
    });
  }, [modelGroups, modelsSettled]);

  const selectedColumn = columns.find((column) => column.id === selectedId) ?? null;
  const selectedModel = models.find((model) => model.id === selectedModelId) ?? null;

  // Model aliases used by models other than the selected one (uniqueness check).
  const takenAliases = useMemo(
    () =>
      new Set(
        models.filter((model) => model.id !== selectedModelId).map((model) => model.alias.trim())
      ),
    [models, selectedModelId]
  );

  // Names taken by columns other than the selected one (uniqueness check).
  const takenNames = useMemo(
    () =>
      new Set(columns.filter((column) => column.id !== selectedId).map((column) => column.name)),
    [columns, selectedId]
  );

  const { nodes, edges } = useMemo(() => buildGraph(columns), [columns]);

  const selectColumn = (id: string | null) => {
    setSelectedId(id);
    if (id !== null) setSelectedModelId(null);
  };
  const selectModel = (id: string | null) => {
    setSelectedModelId(id);
    if (id !== null) setSelectedId(null);
  };

  const hasSeedColumn = columns.some((column) => column.option.columnType === 'seed-dataset');
  const disabledColumnReasons = hasSeedColumn
    ? { 'seed-dataset': 'Only one seed dataset is supported per recipe.' }
    : undefined;

  const handleAddColumn = (selection: AddColumnSelection) => {
    if (selection.columnType === 'seed-dataset' && hasSeedColumn) return;
    const option = findColumnOption(selection);
    if (!option) return;
    const id = `col-${nextId.current++}`;
    setColumns((prev) => {
      const name = defaultColumnName(option, new Set(prev.map((column) => column.name)));
      return [...prev, { id, option, name, values: {} }];
    });
    selectColumn(id);
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

  const handleAddModel = (selection: ModelSelection, provider: string) => {
    const id = `model-${nextModelId.current++}`;
    setModels((prev) => [
      ...prev,
      builderModelFromSelection(
        id,
        selection,
        provider,
        new Set(prev.map((model) => model.alias.trim()))
      ),
    ]);
    selectModel(id);
  };

  const patchModel = (id: string, patch: BuilderModelPatch) =>
    setModels((prev) => prev.map((model) => (model.id === id ? { ...model, ...patch } : model)));

  const removeModel = (id: string) => {
    setModels((prev) => prev.filter((model) => model.id !== id));
    setSelectedModelId((current) => (current === id ? null : current));
  };

  return {
    columns,
    models,
    selectedColumn,
    selectedModel,
    selectedModelId,
    focusId,
    paletteTab,
    setPaletteTab,
    nodes,
    edges,
    takenNames,
    takenAliases,
    disabledColumnReasons,
    selectColumn,
    selectModel,
    handleAddColumn,
    patchColumn,
    removeColumn,
    handleAddModel,
    patchModel,
    removeModel,
  };
};
