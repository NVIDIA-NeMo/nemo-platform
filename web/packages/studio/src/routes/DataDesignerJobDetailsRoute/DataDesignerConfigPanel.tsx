// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { Banner, Divider, SidePanel, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import {
  BUILDER_CONFIG_FILENAME,
  formatColumnTypeBreakdown,
  summarizeBuilderConfig,
  type BuilderConfigSummary,
} from '@studio/routes/DataDesignerJobDetailsRoute/builderConfig';
import { useDataDesignerArtifactsFileset } from '@studio/routes/DataDesignerJobDetailsRoute/useDataDesignerArtifactsFileset';
import { useMemo, type FC } from 'react';

export interface DataDesignerConfigPanelProps {
  open: boolean;
  onClose: () => void;
}

const ConfigSummary: FC<{ summary: BuilderConfigSummary }> = ({ summary }) => (
  <Stack gap="density-xl">
    <Stack gap="density-md">
      <Text kind="label/semibold/md">Overview</Text>
      <KVPair
        label="Columns"
        value={
          summary.columnCount > 0
            ? `${summary.columnCount} (${formatColumnTypeBreakdown(summary)})`
            : '0'
        }
      />
      {summary.seed ? (
        <KVPair
          label="Seed dataset"
          value={
            summary.seed.samplingStrategy
              ? `${summary.seed.type} · ${summary.seed.samplingStrategy}`
              : summary.seed.type
          }
        />
      ) : null}
      <KVPair label="Constraints" value={String(summary.constraintCount)} />
      <KVPair label="Profilers" value={String(summary.profilerCount)} />
      <KVPair
        label="Processors"
        value={summary.processorNames.length > 0 ? summary.processorNames.join(', ') : '0'}
      />
      {summary.libraryVersion ? (
        <KVPair label="Library version" value={summary.libraryVersion} />
      ) : null}
    </Stack>

    {summary.models.length > 0 ? (
      <>
        <Divider />
        <Stack gap="density-md">
          <Text kind="label/semibold/md">Models</Text>
          {summary.models.map((model, index) => (
            <KVPair
              key={`${model.alias}-${index}`}
              label={model.alias}
              value={model.provider ? `${model.model} (${model.provider})` : model.model}
            />
          ))}
        </Stack>
      </>
    ) : null}

    {summary.columns.length > 0 ? (
      <>
        <Divider />
        <Stack gap="density-md">
          <Text kind="label/semibold/md">Columns</Text>
          {summary.columns.map((column, index) => (
            <KVPair
              key={`${column.name}-${index}`}
              label={column.name}
              value={column.modelAlias ? `${column.type} · ${column.modelAlias}` : column.type}
            />
          ))}
        </Stack>
      </>
    ) : null}
  </Stack>
);

export const DataDesignerConfigPanel: FC<DataDesignerConfigPanelProps> = ({ open, onClose }) => {
  const { filesetWorkspace, filesetName, files, isResultsLoading, isFilesLoading } =
    useDataDesignerArtifactsFileset();

  const builderConfigPath = useMemo(
    () =>
      files.find(
        (file) =>
          file.path === BUILDER_CONFIG_FILENAME || file.path.endsWith(`/${BUILDER_CONFIG_FILENAME}`)
      )?.path,
    [files]
  );

  const {
    data: rawContent,
    isLoading: isContentLoading,
    isError: isContentError,
  } = useDatasetFileContent({
    workspace: filesetWorkspace,
    name: filesetName,
    path: builderConfigPath ?? '',
    enabled: open && Boolean(filesetWorkspace && filesetName && builderConfigPath),
  });

  const summary = useMemo(() => {
    if (!rawContent) {
      return null;
    }
    try {
      return summarizeBuilderConfig(JSON.parse(rawContent) as unknown);
    } catch {
      return null;
    }
  }, [rawContent]);

  const isResolving = isResultsLoading || isFilesLoading;
  const isLoading = isResolving || (Boolean(builderConfigPath) && isContentLoading);

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      onClose();
    }
  };

  const renderBody = () => {
    if (isLoading) {
      return (
        <Stack align="center" gap="density-md" padding="density-xl">
          <Spinner aria-label="Loading job config" />
          <Text kind="body/regular/sm" className="text-muted">
            Loading job config...
          </Text>
        </Stack>
      );
    }

    if (!builderConfigPath) {
      return (
        <Text kind="body/regular/md" className="text-muted">
          No <code>{BUILDER_CONFIG_FILENAME}</code> was found in this job's output fileset. The
          config is available once the job has produced its artifacts.
        </Text>
      );
    }

    if (isContentError || !summary) {
      return (
        <Banner kind="inline" status="error" title="Could not read job config">
          The <code>{BUILDER_CONFIG_FILENAME}</code> file could not be loaded or parsed.
        </Banner>
      );
    }

    return <ConfigSummary summary={summary} />;
  };

  return (
    <SidePanel
      side="right"
      open={open}
      onOpenChange={handleOpenChange}
      slotHeading="Job config"
      bordered
      modal
      className="max-w-[560px] w-full"
    >
      <Stack gap="density-md">{renderBody()}</Stack>
    </SidePanel>
  );
};
