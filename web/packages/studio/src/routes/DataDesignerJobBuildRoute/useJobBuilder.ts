// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import type { AddColumnSelection } from '@studio/components/AddColumnPalette/types';
import type { FilesetTemplate } from '@studio/components/CreateFilesetStart/types';
import {
  type BuilderColumn,
  buildColumnsFromTemplate,
  defaultColumnName,
  findColumnOption,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';
import {
  type BuilderModel,
  buildModelsFromTemplate,
  builderModelFromSelection,
  fetchAutoFillCandidates,
  resolveTemplateModel,
} from '@studio/routes/DataDesignerJobBuildRoute/models';
import { useCallback, useEffect, useRef, useState } from 'react';
import { type UseFormReturn, useFieldArray, useForm } from 'react-hook-form';

/** Which palette the left aside shows. */
export type PaletteTab = 'columns' | 'models';

/** All mutable values in the build route, owned by React Hook Form. */
export interface JobBuilderFormValues {
  name: string;
  rows: string;
  columns: BuilderColumn[];
  models: BuilderModel[];
}

export interface JobBuilderValues {
  columns: BuilderColumn[];
  models: BuilderModel[];
  name: string;
  rows: string;
}

/**
 * Fully-formed initial builder state used to clone an existing job. When present it seeds the
 * form instead of the template, so the canvas opens pre-filled with the source job's schema.
 */
export interface JobBuilderSeed {
  name: string;
  rows: string;
  columns: BuilderColumn[];
  models: BuilderModel[];
}

/**
 * Column/model state for the recipe builder. Selecting a column and selecting a model are
 * mutually exclusive — only one config panel shows at a time.
 *
 * Job-level concerns (name, row count, validation, preview, submit) live in the route so
 * this hook stays a pure graph-editing store.
 *
 * A template's seeded models are auto-filled once from `workspace`, resolving each spec with a
 * targeted lookup rather than the whole model catalogue.
 *
 * `seed`, when provided (cloning a job), takes precedence over the template and pre-fills the
 * form with the source job's columns, models, name, and row count.
 */
export const useJobBuilder = (
  template: FilesetTemplate | null,
  workspace: string,
  seed: JobBuilderSeed | null = null
) => {
  // Seed once from the clone source, else the template (if any). `useForm` keeps these values
  // outside the route's render cycle, so a field edit notifies only subscribing components.
  const initialColumns = useRef(
    seed ? seed.columns : template ? buildColumnsFromTemplate(template.columns) : []
  );
  const initialModels = useRef(seed ? seed.models : buildModelsFromTemplate(template?.models));
  const form = useForm<JobBuilderFormValues>({
    defaultValues: {
      name: seed?.name ?? template?.id ?? 'untitled-dataset',
      rows: seed?.rows ?? '100',
      columns: initialColumns.current,
      models: initialModels.current,
    },
  });
  const { getValues, setValue } = form;
  const {
    fields: columnFields,
    append: appendColumn,
    remove: removeColumnField,
  } = useFieldArray({
    control: form.control,
    name: 'columns',
    keyName: 'fieldId',
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Set only when a column is added, so the canvas centers new nodes but not clicked ones.
  const [focusId, setFocusId] = useState<string | null>(null);
  // Continue numbering after any preloaded template columns so ids stay unique.
  const nextId = useRef(initialColumns.current.length);

  // The models referenced by LLM columns via `model_alias`; part of the same job config.
  // Seeded once from the template (if any); providers/models are auto-filled below.
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const nextModelId = useRef(initialModels.current.length);
  const [paletteTab, setPaletteTab] = useState<PaletteTab>('columns');

  const autoFilled = useRef(false);
  useEffect(() => {
    if (autoFilled.current || !workspace) return;
    const pending = getValues('models').filter((model) => !model.provider);
    if (pending.length === 0) return;
    autoFilled.current = true;

    let cancelled = false;
    void (async () => {
      const resolutions = await Promise.all(
        pending.map(async (model) => {
          const preferred = model.model || undefined;
          const candidates = await fetchAutoFillCandidates(workspace, preferred);
          return [model.id, resolveTemplateModel(candidates, preferred)] as const;
        })
      );
      if (cancelled) return;
      const byId = new Map(resolutions);
      setValue(
        'models',
        getValues('models').map((model) => {
          if (!byId.has(model.id)) return model;
          const resolved = byId.get(model.id);
          return resolved ? { ...model, ...resolved } : { ...model, model: '' };
        })
      );
    })();

    return () => {
      cancelled = true;
    };
  }, [getValues, setValue, workspace]);

  const selectColumn = useCallback((id: string | null) => {
    setSelectedId(id);
    if (id !== null) setSelectedModelId(null);
  }, []);
  const selectModel = useCallback((id: string | null) => {
    setSelectedModelId(id);
    if (id !== null) setSelectedId(null);
  }, []);

  const handleAddColumn = useCallback(
    (selection: AddColumnSelection) => {
      const columns = getValues('columns');
      if (
        selection.columnType === 'seed-dataset' &&
        columns.some((column) => column.option.columnType === 'seed-dataset')
      ) {
        return;
      }
      const option = findColumnOption(selection);
      if (!option) return;
      const id = `col-${nextId.current++}`;
      const name = defaultColumnName(option, new Set(columns.map((column) => column.name)));
      appendColumn({ id, option, name, values: {} });
      selectColumn(id);
      setFocusId(id);
    },
    [appendColumn, getValues, selectColumn]
  );

  const removeColumn = useCallback(
    (id: string) => {
      const index = getValues('columns').findIndex((column) => column.id === id);
      if (index >= 0) removeColumnField(index);
      setSelectedId((current) => (current === id ? null : current));
    },
    [getValues, removeColumnField]
  );

  const handleAddModel = useCallback(
    (selection: ModelSelection, provider: string) => {
      const id = `model-${nextModelId.current++}`;
      const models = getValues('models');
      setValue('models', [
        ...models,
        builderModelFromSelection(
          id,
          selection,
          provider,
          new Set(models.map((model) => model.alias.trim()))
        ),
      ]);
      selectModel(id);
    },
    [getValues, selectModel, setValue]
  );

  const removeModel = useCallback(
    (id: string) => {
      setValue(
        'models',
        getValues('models').filter((model) => model.id !== id)
      );
      setSelectedModelId((current) => (current === id ? null : current));
    },
    [getValues, setValue]
  );

  const getBuilderValues = useCallback((): JobBuilderValues => {
    const values = getValues();
    return {
      name: values.name,
      rows: values.rows,
      columns: values.columns,
      models: values.models,
    };
  }, [getValues]);

  return {
    form: form as UseFormReturn<JobBuilderFormValues>,
    getBuilderValues,
    columnCount: columnFields.length,
    selectedColumnId: selectedId,
    selectedModelId,
    focusId,
    paletteTab,
    setPaletteTab,
    selectColumn,
    selectModel,
    handleAddColumn,
    removeColumn,
    handleAddModel,
    removeModel,
  };
};
