// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { useFilesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import { Flex, FormField, Select, Tag, Text } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  SAMPLING_STRATEGY_OPTIONS,
  SEED_AVAILABLE_COLUMNS_KEY,
  SEED_FILE_PATH_KEY,
  SEED_FILESET_REF_KEY,
  SEED_SAMPLING_STRATEGY_KEY,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';
import { FilesetSearchableSelect } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/FilesetSearchableSelect';
import { getContentColumns, getFileExtension } from '@studio/util/files';
import { type FC, useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';

export interface SeedDatasetConfigProps {
  /** The seed-dataset column's current field values. */
  values: Record<string, string>;
  /** Merges the given keys into the column's values (parent spreads onto the rest). */
  onPatch: (patch: Record<string, string>) => void;
}

interface SeedFilesetForm {
  [SEED_FILESET_REF_KEY]: string;
}

/**
 * Config controls for a seed-dataset column, sourced from a platform fileset.
 *
 * The SDK's `FilesetFileSeedSource` takes a single composite `path`
 * (`{workspace}/{fileset}#{file}`); rather than have the user hand-type that, this collects the
 * fileset and the in-fileset file as separate picks (stored under {@link SEED_FILESET_REF_KEY} /
 * {@link SEED_FILE_PATH_KEY}). `buildSeedConfig` assembles them into the composite path at submit.
 *
 * The fileset uses {@link FilesetSearchableSelect} for server-side `$like` search + paging. It is
 * react-hook-form based, so a local form holds its value and pushes changes up via `onPatch`.
 * The panel keys this component by column id, so each column mounts a form seeded from its values.
 */
export const SeedDatasetConfig: FC<SeedDatasetConfigProps> = ({ values, onPatch }) => {
  const workspace = useWorkspaceFromPath();
  const filesetRef = values[SEED_FILESET_REF_KEY] ?? '';
  const filePath = values[SEED_FILE_PATH_KEY] ?? '';
  const samplingStrategy = values[SEED_SAMPLING_STRATEGY_KEY] ?? '';

  const { control, watch } = useForm<SeedFilesetForm>({
    defaultValues: { [SEED_FILESET_REF_KEY]: filesetRef },
  });

  useEffect(() => {
    const subscription = watch((formValues, { name }) => {
      if (name !== SEED_FILESET_REF_KEY) return;
      onPatch({
        [SEED_FILESET_REF_KEY]: formValues[SEED_FILESET_REF_KEY] ?? '',
        [SEED_FILE_PATH_KEY]: '',
        [SEED_AVAILABLE_COLUMNS_KEY]: '',
      });
    });
    return () => subscription.unsubscribe();
  }, [watch, onPatch]);

  const { workspace: filesetWorkspace, name: filesetName } = getPartsFromReference(filesetRef);
  const { data: filesResponse, isLoading: isLoadingFiles } = useFilesListFilesetFiles(
    filesetWorkspace,
    filesetName,
    undefined,
    { query: { enabled: Boolean(filesetRef) } }
  );
  const fileItems = useMemo(
    () => (filesResponse?.data ?? []).map((file) => ({ children: file.path, value: file.path })),
    [filesResponse?.data]
  );

  const isParquet = filePath.endsWith('parquet');
  const {
    data: fileContent,
    isLoading: isLoadingSchema,
    isError: isSchemaError,
  } = useDatasetFileContent({
    workspace: filesetWorkspace,
    name: filesetName,
    path: filePath,
    range: isParquet ? [0, 1] : undefined,
    enabled: Boolean(filesetRef && filePath),
  });
  const availableColumns = useMemo(() => {
    if (!fileContent) return [];
    const fileType = isParquet ? 'jsonl' : (getFileExtension(filePath) ?? undefined);
    return getContentColumns(fileContent, fileType);
  }, [fileContent, filePath, isParquet]);

  useEffect(() => {
    const joined = availableColumns.join(',');
    if ((values[SEED_AVAILABLE_COLUMNS_KEY] ?? '') !== joined) {
      onPatch({ [SEED_AVAILABLE_COLUMNS_KEY]: joined });
    }
  }, [availableColumns, values, onPatch]);

  const samplingItems = SAMPLING_STRATEGY_OPTIONS.map((option) => ({
    children: option.label,
    value: option.value,
  }));

  return (
    <>
      <FilesetSearchableSelect
        workspace={workspace}
        useControllerProps={{ control, name: SEED_FILESET_REF_KEY }}
        formFieldProps={{
          slotLabel: 'Fileset',
          slotInfo: 'The platform fileset to seed rows from.',
        }}
        triggerPlaceholder="Select a fileset"
      />

      <FormField
        slotLabel="File"
        required
        slotInfo="The file within the fileset to read rows from."
      >
        <Select
          aria-label="Seed file"
          disabled={!filesetRef}
          items={fileItems}
          value={filePath || undefined}
          onValueChange={(value) =>
            onPatch({
              [SEED_FILE_PATH_KEY]: value ?? '',
              [SEED_AVAILABLE_COLUMNS_KEY]: '',
            })
          }
          placeholder={
            !filesetRef
              ? 'Select a fileset first'
              : isLoadingFiles
                ? 'Loading files…'
                : 'Select a file'
          }
        />
      </FormField>

      {filePath && (
        <FormField
          slotLabel="Available columns"
          slotInfo="Columns provided by the seed file. Reference them from other columns with {{ name }}."
        >
          {isLoadingSchema ? (
            <Text kind="body/regular/sm" className="text-secondary">
              Reading columns…
            </Text>
          ) : isSchemaError ? (
            <Text kind="body/regular/sm" className="text-feedback-danger">
              Couldn't read columns from this file.
            </Text>
          ) : availableColumns.length === 0 ? (
            <Text kind="body/regular/sm" className="text-secondary">
              No columns found in this file.
            </Text>
          ) : (
            <Flex gap="density-xs" className="flex-wrap">
              {availableColumns.map((name) => (
                <Tag key={name} kind="outline" color="gray" readOnly>
                  {name}
                </Tag>
              ))}
            </Flex>
          )}
        </FormField>
      )}

      <FormField
        slotLabel="Sampling strategy"
        slotInfo="How rows are read from the seed dataset. Defaults to ordered."
      >
        <Select
          aria-label="Sampling strategy"
          items={samplingItems}
          value={samplingStrategy || undefined}
          onValueChange={(value) => onPatch({ [SEED_SAMPLING_STRATEGY_KEY]: value ?? '' })}
          placeholder="Ordered"
        />
      </FormField>
    </>
  );
};
