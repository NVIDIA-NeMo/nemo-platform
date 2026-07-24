// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAllModels } from '@nemo/common/src/api/models/useModels';
import { DEFAULT_LARGE_PAGE_SIZE } from '@nemo/common/src/constants/api';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import { useDataDesignerCreateJob } from '@nemo/sdk/generated/data-designer/api';
import { useModelsListProviders } from '@nemo/sdk/generated/platform/api';
import { Flex, Stack } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { findTemplate } from '@studio/components/CreateFilesetStart/templates';
import { usePreview } from '@studio/components/NewDataDesignerJobForm/usePreview';
import { getCloneJobRequestFromState } from '@studio/components/NewDataDesignerJobForm/utils';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { BuilderCanvas } from '@studio/routes/DataDesignerJobBuildRoute/BuilderCanvas';
import { BuilderConfigPane } from '@studio/routes/DataDesignerJobBuildRoute/BuilderConfigPane';
import { BuilderDetailsPanel } from '@studio/routes/DataDesignerJobBuildRoute/BuilderDetailsPanel';
import { BuilderPalette } from '@studio/routes/DataDesignerJobBuildRoute/BuilderPalette';
import {
  BuilderToolbar,
  type BuilderViewMode,
} from '@studio/routes/DataDesignerJobBuildRoute/BuilderToolbar';
import {
  buildColumnsFromConfig,
  buildDataDesignerConfig,
  validateColumns,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';
import {
  buildModelsFromConfig,
  buildServedModelNames,
  validateModels,
} from '@studio/routes/DataDesignerJobBuildRoute/models';
import { SchemaList } from '@studio/routes/DataDesignerJobBuildRoute/SchemaList';
import {
  type JobBuilderSeed,
  useJobBuilder,
} from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import {
  getDataDesignerJobDetailsRoute,
  getDataDesignerJobListRoute,
  getNewDataDesignerJobRoute,
} from '@studio/routes/utils';
import { type FC, useCallback, useMemo, useState } from 'react';
import { FormProvider } from 'react-hook-form';
import { useAuth } from 'react-oidc-context';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';

/**
 * Edges are derived from entered values: Jinja2 `{{ column_name }}` references (and
 * column-name fields) draw edges so the graph reflects data dependencies, not add order.
 */
export const DataDesignerJobBuildRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const { state: locationState } = useLocation();

  const template = useMemo(() => {
    const templateId = searchParams.get('template');
    return templateId ? (findTemplate(templateId) ?? null) : null;
  }, [searchParams]);

  const cloneSeed = useMemo<JobBuilderSeed | null>(() => {
    const cloneRequest = getCloneJobRequestFromState(locationState);
    if (!cloneRequest?.spec) return null;
    const { config, num_records } = cloneRequest.spec;
    return {
      name: cloneRequest.name ?? 'untitled-dataset',
      rows: String(num_records),
      columns: buildColumnsFromConfig(config),
      models: buildModelsFromConfig(config.model_configs),
    };
  }, [locationState]);

  const heading = cloneSeed
    ? `Clone of ${cloneSeed.name}`
    : template
      ? template.title
      : 'Build from scratch';

  useBreadcrumbs({
    items: [
      { href: getDataDesignerJobListRoute(workspace), slotLabel: 'Data Designer' },
      { href: getNewDataDesignerJobRoute(workspace), slotLabel: 'New fileset' },
      { slotLabel: heading },
    ],
  });

  const {
    data: modelsData,
    isLoading: isLoadingModels,
    hasNextPage,
    isFetchingNextPage,
  } = useAllModels({ workspace });
  const modelGroups = useMemo(
    () =>
      groupModelsByWorkspace(modelsData?.pages.flatMap((page) => page.data ?? []) ?? [], {
        sort: true,
      }),
    [modelsData?.pages]
  );
  const modelsSettled = !isLoadingModels && !hasNextPage && !isFetchingNextPage;

  const builder = useJobBuilder(template, modelGroups, modelsSettled, cloneSeed);
  const { data: providersPage } = useModelsListProviders(
    workspace,
    { page_size: DEFAULT_LARGE_PAGE_SIZE },
    { query: {} }
  );
  const servedModelNames = useMemo(
    () => buildServedModelNames(providersPage?.data ?? []),
    [providersPage?.data]
  );

  const [viewMode, setViewMode] = useState<BuilderViewMode>('list');
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  const validateAndCollectErrors = useCallback(() => {
    const { columns, models, name, rows } = builder.getBuilderValues();
    const numRecords = Number(rows);
    const errors = [...validateColumns(columns), ...validateModels(models)];
    if (!name.trim()) {
      errors.push('Fileset name is required.');
    }
    if (!Number.isInteger(numRecords) || numRecords < 1) {
      errors.push('Records to generate must be a whole number of at least 1.');
    }
    setValidationErrors(errors);
    setIsDetailsOpen(true);
    return errors;
  }, [builder]);

  const getCurrentConfig = useCallback(() => {
    const { columns, models } = builder.getBuilderValues();
    return validateColumns(columns).length === 0 && validateModels(models).length === 0
      ? buildDataDesignerConfig(columns, models, servedModelNames)
      : undefined;
  }, [builder, servedModelNames]);
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
    const { columns, models, name, rows } = builder.getBuilderValues();

    try {
      const created = await createJob.mutateAsync({
        workspace,
        data: {
          name,
          spec: {
            num_records: Number(rows),
            config: buildDataDesignerConfig(columns, models, servedModelNames),
          },
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
      <FormProvider {...builder.form}>
        <Stack className=" h-full">
          <BuilderToolbar
            templateTag={template?.tag}
            columnCount={builder.columnCount}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
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
              selectedModelId={builder.selectedModelId}
              modelGroups={modelGroups}
              isLoadingModels={isLoadingModels}
              onAddColumn={builder.handleAddColumn}
              onAddModel={builder.handleAddModel}
              onSelectModel={builder.selectModel}
            />

            <div className="relative min-w-0 flex-1">
              {viewMode === 'list' ? (
                <SchemaList
                  selectedId={builder.selectedColumnId}
                  onSelect={builder.selectColumn}
                  onDelete={builder.removeColumn}
                />
              ) : (
                <BuilderCanvas
                  focusNodeId={builder.focusId}
                  onNodeClick={builder.selectColumn}
                  onNodeDelete={builder.removeColumn}
                />
              )}
            </div>

            <BuilderConfigPane
              selectedColumnId={builder.selectedColumnId}
              selectedModelId={builder.selectedModelId}
              modelGroups={modelGroups}
              isLoadingModels={isLoadingModels}
              onColumnRemove={() =>
                builder.selectedColumnId && builder.removeColumn(builder.selectedColumnId)
              }
              onColumnClose={() => builder.selectColumn(null)}
              onModelRemove={() =>
                builder.selectedModelId && builder.removeModel(builder.selectedModelId)
              }
              onModelClose={() => builder.selectModel(null)}
            />
          </Flex>
        </Stack>
      </FormProvider>
    </AccessibleTitle>
  );
};
