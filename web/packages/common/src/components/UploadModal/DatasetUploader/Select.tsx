// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getFileExtension } from '@nemo/common/src/components/DatasetFileSelect/utils';
import { FilesetSearchableSelect } from '@nemo/common/src/components/FilesetSearchableSelect';
import type { SelectItemOption } from '@nemo/common/src/components/form/ControlledSearchableSelect';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useUploadModalContext } from '@nemo/common/src/components/UploadModal/Context/useUploadModalContext';
import { getExistingFileId } from '@nemo/common/src/components/UploadModal/utils';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { filesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Flex, Text } from '@nvidia/foundations-react-core';
import { FC, useCallback, useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';

interface Props {
  /**
   * The workspace (formerly "project" or "namespace") to filter filesets by.
   */
  project: string;
  disabled?: boolean;
  error?: string;
}

/** Sentinel option value for "create a new dataset". */
const NEW_DATASET_VALUE = 'new';

const GROUP_NEW = 'new';
const GROUP_EXISTING = 'existing';

export const DatasetSelect: FC<Props> = ({ project, disabled, error }) => {
  const [state, dispatch] = useUploadModalContext();
  const {
    dataset,
    allowNewDataset,
    acceptableFileTypes,
    autoSelectFirstAcceptable,
    showUpdatedAt,
  } = state;
  const purpose = state.filesetPurpose ?? 'dataset';
  const label = state.datasetLabel ?? 'Dataset';

  // Extract workspace from project (project format is "workspace/name" or just "workspace")
  const workspace = project.includes('/') ? project.split('/')[0] : project;

  const selectedDatasetOption = useMemo(() => {
    if (dataset?.type === 'new') return NEW_DATASET_VALUE;
    return dataset?.dataset ? getEntityReference(dataset.dataset) : '';
  }, [dataset]);

  const { control, setValue } = useForm<{ dataset: string }>({
    defaultValues: { dataset: selectedDatasetOption },
  });

  useEffect(() => {
    setValue('dataset', selectedDatasetOption);
  }, [selectedDatasetOption, setValue]);

  const handleDatasetSelect = async (datasetId: string, fileset?: FilesetOutput) => {
    if (datasetId === NEW_DATASET_VALUE) {
      dispatch({ type: 'SET_DATASET', payload: { type: 'new', name: '' } });
      return;
    }
    if (!fileset) return;
    dispatch({ type: 'SET_FETCHING', payload: true });
    dispatch({ type: 'SET_DATASET', payload: { type: 'existing', dataset: fileset } });
    // Fetch fileset files and set them in the state
    try {
      const filesResponse = await filesListFilesetFiles(fileset.workspace, fileset.name);
      const filesetFiles = filesResponse.data ?? [];
      const uploadFiles = filesetFiles.map(
        (file) => ({ id: getExistingFileId(file), type: 'existing', file }) as const
      );
      dispatch({ type: 'SET_FILES', payload: uploadFiles });
      // Auto-select the first root-level accepted file (only when >1, since
      // the reducer already auto-selects a lone file).
      if (autoSelectFirstAcceptable && uploadFiles.length > 1) {
        const allowed = acceptableFileTypes.map((t) => t.toLowerCase());
        const target = uploadFiles.find((f) => {
          const path = f.file.path;
          if (path.includes('/')) return false;
          const ext = getFileExtension(path)?.toLowerCase();
          return !!ext && allowed.includes(ext);
        });
        if (target) dispatch({ type: 'TOGGLE_FILE_SELECTION', payload: target });
      }
      dispatch({ type: 'SET_FETCHING', payload: false });
    } catch (error) {
      console.error('Error fetching dataset files', error);
      dispatch({ type: 'SET_FETCHING', payload: false });
      dispatch({ type: 'SET_ERRORS', payload: { file: 'Error fetching dataset files' } });
    }
  };

  const renderOption = useCallback(
    (fileset: FilesetOutput): SelectItemOption => {
      const ref = getEntityReference(fileset);
      const name = fileset.name ?? '';
      return {
        value: ref,
        label: name,
        group: GROUP_EXISTING,
        ...(showUpdatedAt && fileset.updated_at
          ? {
              render: (
                <Flex gap="density-md" align="center" justify="between" className="w-full">
                  <span>{name}</span>
                  <Text kind="body/regular/xs" color="secondary">
                    <RelativeTime datetime={fileset.updated_at} />
                  </Text>
                </Flex>
              ),
            }
          : {}),
      };
    },
    [showUpdatedAt]
  );

  const leadingOptions = useMemo<SelectItemOption[] | undefined>(
    () =>
      allowNewDataset
        ? [{ value: NEW_DATASET_VALUE, label: 'New Dataset', group: GROUP_NEW }]
        : undefined,
    [allowNewDataset]
  );

  const groupLabels = useMemo<Record<string, string>>(
    () => ({
      ...(allowNewDataset ? { [GROUP_NEW]: `Create ${label}` } : {}),
      [GROUP_EXISTING]: `Existing ${label}s`,
    }),
    [allowNewDataset, label]
  );

  return (
    <FilesetSearchableSelect
      workspace={workspace}
      purpose={purpose}
      useControllerProps={{ control, name: 'dataset' }}
      formFieldProps={{ slotLabel: label, slotError: error }}
      triggerPlaceholder={`Select a ${label.toLowerCase()}`}
      onChange={handleDatasetSelect}
      disabled={disabled}
      leadingOptions={leadingOptions}
      groupLabels={groupLabels}
      renderOption={renderOption}
    />
  );
};
