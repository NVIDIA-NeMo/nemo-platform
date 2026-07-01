// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAllModels } from '@nemo/common/src/api/models/useModels';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import { useDataDesignerCreateJob } from '@nemo/sdk/generated/data-designer/api';
import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { findTemplate } from '@studio/components/CreateFilesetStart/templates';
import { DagCanvas } from '@studio/components/DagCanvas';
import { usePreview } from '@studio/components/NewDataDesignerJobForm/usePreview';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { BuilderConfigPane } from '@studio/routes/DataDesignerJobBuildRoute/BuilderConfigPane';
import { BuilderDetailsPanel } from '@studio/routes/DataDesignerJobBuildRoute/BuilderDetailsPanel';
import { BuilderPalette } from '@studio/routes/DataDesignerJobBuildRoute/BuilderPalette';
import { BuilderToolbar } from '@studio/routes/DataDesignerJobBuildRoute/BuilderToolbar';
import {
  buildDataDesignerConfig,
  validateColumns,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';
import { validateModels } from '@studio/routes/DataDesignerJobBuildRoute/models';
import { useJobBuilder } from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import {
  getDataDesignerJobDetailsRoute,
  getDataDesignerJobListRoute,
  getNewDataDesignerJobRoute,
} from '@studio/routes/utils';
import { type FC, useCallback, useMemo, useState } from 'react';
import { useAuth } from 'react-oidc-context';
import { useNavigate, useSearchParams } from 'react-router-dom';

/**
 * The "Build from scratch" column builder. Composes the {@link BuilderPalette} (left),
 * the {@link DagCanvas} recipe graph (center), and a {@link BuilderConfigPane} that opens
 * on the right when a column/model is added or a node is clicked — so the canvas stays
 * visible while it is configured.
 *
 * Edges are derived from the entered values: a column that references another via a
 * Jinja2 `{{ column_name }}` token (or a column-name field) gets an edge from the
 * referenced column, so the graph reflects real data dependencies rather than add order.
 */
export const DataDesignerJobBuildRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const { user } = useAuth();
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

  // Platform models to populate the model config panel's ModelSelectV2 dropdown and to
  // auto-fill a template's seeded models.
  const { data: modelsData, isLoading: isLoadingModels } = useAllModels({ workspace });
  const modelGroups = useMemo(
    () =>
      groupModelsByWorkspace(modelsData?.pages.flatMap((page) => page.data ?? []) ?? [], {
        sort: true,
      }),
    [modelsData?.pages]
  );

  const builder = useJobBuilder(template, modelGroups);
  const { columns, models } = builder;

  const [name, setName] = useState(() => template?.id ?? 'untitled-dataset');
  const [rows, setRows] = useState('100');
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  // Whether the errors/preview panel below the toolbar is expanded. Runs that produce
  // output re-open it; the user can collapse it again to focus on the canvas.
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  const validateAndCollectErrors = useCallback(() => {
    const numRecords = Number(rows);
    const errors = [...validateColumns(columns), ...validateModels(models)];
    if (!Number.isInteger(numRecords) || numRecords < 1) {
      errors.push('Records to generate must be a whole number of at least 1.');
    }
    setValidationErrors(errors);
    setIsDetailsOpen(true);
    return errors;
  }, [columns, models, rows]);

  const getCurrentConfig = useCallback(
    () =>
      validateColumns(columns).length === 0 && validateModels(models).length === 0
        ? buildDataDesignerConfig(columns, models)
        : undefined,
    [columns, models]
  );
  const { previewLogs, isPreviewing, runPreview } = usePreview({
    workspace,
    accessToken: user?.access_token ?? undefined,
    getCurrentConfig,
  });

  const handlePreview = () => {
    if (validateAndCollectErrors().length > 0) return;
    setIsDetailsOpen(true);
    void runPreview();
  };

  const createJob = useDataDesignerCreateJob();
  const submitError = createJob.error ? getErrorMessage(createJob.error) : null;

  const handleSubmit = async () => {
    if (validateAndCollectErrors().length > 0) return;

    try {
      const created = await createJob.mutateAsync({
        workspace,
        data: {
          name,
          spec: { num_records: Number(rows), config: buildDataDesignerConfig(columns, models) },
        },
      });
      if (created?.name) {
        navigate(getDataDesignerJobDetailsRoute(workspace, created.name));
      } else {
        navigate(getDataDesignerJobListRoute(workspace));
      }
    } catch {
      setIsDetailsOpen(true);
      // Error surfaced via createJob.error / submitError below.
    }
  };

  return (
    <AccessibleTitle title={heading}>
      <Stack className=" h-full">
        <BuilderToolbar
          name={name}
          onNameChange={setName}
          columnCount={columns.length}
          templateTag={template?.tag}
          rows={rows}
          onRowsChange={setRows}
          onPreview={handlePreview}
          isPreviewing={isPreviewing}
          onSubmit={handleSubmit}
          isSubmitting={createJob.isPending}
        />

        <BuilderDetailsPanel
          validationErrors={validationErrors}
          submitError={submitError}
          previewLogs={previewLogs}
          isOpen={isDetailsOpen}
          onToggle={() => setIsDetailsOpen((open) => !open)}
        />

        <Flex className="min-h-0 border-t border-base h-full">
          <BuilderPalette
            tab={builder.paletteTab}
            onTabChange={builder.setPaletteTab}
            models={models}
            selectedModelId={builder.selectedModelId}
            modelGroups={modelGroups}
            isLoadingModels={isLoadingModels}
            onAddColumn={builder.handleAddColumn}
            onAddModel={builder.handleAddModel}
            onSelectModel={builder.selectModel}
          />

          <div className="relative min-w-0 flex-1">
            {columns.length === 0 ? (
              <Flex align="center" justify="center" className="h-full">
                <Text kind="body/regular/md" className="text-secondary">
                  Empty canvas — add a column from the left to get started.
                </Text>
              </Flex>
            ) : (
              <DagCanvas
                nodes={builder.nodes}
                edges={builder.edges}
                onNodeClick={builder.selectColumn}
                onNodeDelete={builder.removeColumn}
                focusNodeId={builder.focusId}
              />
            )}
          </div>

          <BuilderConfigPane
            selectedColumn={builder.selectedColumn}
            selectedModel={builder.selectedModel}
            takenNames={builder.takenNames}
            takenAliases={builder.takenAliases}
            modelGroups={modelGroups}
            isLoadingModels={isLoadingModels}
            onColumnChange={(patch) =>
              builder.selectedColumn && builder.patchColumn(builder.selectedColumn.id, patch)
            }
            onColumnRemove={() =>
              builder.selectedColumn && builder.removeColumn(builder.selectedColumn.id)
            }
            onColumnClose={() => builder.selectColumn(null)}
            onModelChange={(patch) =>
              builder.selectedModel && builder.patchModel(builder.selectedModel.id, patch)
            }
            onModelRemove={() =>
              builder.selectedModel && builder.removeModel(builder.selectedModel.id)
            }
            onModelClose={() => builder.selectModel(null)}
          />
        </Flex>
      </Stack>
    </AccessibleTitle>
  );
};
