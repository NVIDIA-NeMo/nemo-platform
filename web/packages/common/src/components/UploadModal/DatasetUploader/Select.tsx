// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useUploadModalContext } from '@nemo/common/src/components/UploadModal/Context/useUploadModalContext';
import { getExistingFileId } from '@nemo/common/src/components/UploadModal/utils';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { filesListFilesetFiles, useFilesListFilesets } from '@nemo/sdk/generated/platform/api';
import { FilesetOutput, FilesetPurpose } from '@nemo/sdk/generated/platform/schema';
import { Flex, FormField, Select, Text } from '@nvidia/foundations-react-core';
import { CircleAlert } from 'lucide-react';
import { FC, useMemo } from 'react';

interface Props {
  /**
   * The workspace (formerly "project" or "namespace") to filter filesets by.
   */
  project: string;
  disabled?: boolean;
  error?: string;
  filesetPurposeFilter?: FilesetPurpose | null;
  filesetLabel?: string;
}

const filesetToOption = (fileset: FilesetOutput) => ({
  children: fileset.name ?? '',
  value: getEntityReference(fileset),
});

export const DatasetSelect: FC<Props> = ({
  project,
  disabled,
  error,
  filesetPurposeFilter = FilesetPurpose.dataset,
  filesetLabel = 'Dataset',
}) => {
  const [state, dispatch] = useUploadModalContext();
  const { dataset, allowNewDataset } = state;

  // Extract workspace from project (project format is "workspace/name" or just "workspace")
  const workspace = project.includes('/') ? project.split('/')[0] : project;

  const {
    data: filesetsResponse,
    isLoading,
    isError,
  } = useFilesListFilesets(workspace, {
    /**
     * For now, we use an arbitrarily large page size to fetch all filesets, to enable client-side search.
     * When the API implements server-side search, update this implementation to leverage
     * server-side search and pagination.
     */
    page_size: 100, // v2 API max is 100
    sort: 'created_at',
    ...(filesetPurposeFilter ? { filter: { purpose: filesetPurposeFilter } } : {}),
  });

  const filesets = useMemo(() => filesetsResponse?.data ?? [], [filesetsResponse]);

  const selectedDatasetOption = useMemo(() => {
    if (dataset?.type === 'new') {
      return 'new';
    }
    return dataset?.dataset?.name ?? '';
  }, [dataset]);

  const handleDatasetSelect = async (datasetId: string) => {
    if (datasetId === 'new') {
      dispatch({ type: 'SET_DATASET', payload: { type: 'new', name: '' } });
    } else {
      const fileset = filesets?.find((fs) => getEntityReference(fs) === datasetId);
      if (!fileset) return;
      dispatch({ type: 'SET_FETCHING', payload: true });
      dispatch({ type: 'SET_DATASET', payload: { type: 'existing', dataset: fileset } });
      // Fetch fileset files and set them in the state
      try {
        const filesResponse = await filesListFilesetFiles(fileset.workspace, fileset.name);
        const filesetFiles = filesResponse.data ?? [];
        dispatch({
          type: 'SET_FILES',
          payload: filesetFiles.map((file) => ({
            id: getExistingFileId(file),
            type: 'existing',
            file,
          })),
        });
        dispatch({ type: 'SET_FETCHING', payload: false });
      } catch (error) {
        console.error('Error fetching dataset files', error);
        dispatch({ type: 'SET_FETCHING', payload: false });
        dispatch({ type: 'SET_ERRORS', payload: { file: 'Error fetching dataset files' } });
      }
    }
  };

  const datasetOptions = useMemo(() => {
    const filesetCollectionLabel = filesetLabel === 'Dataset' ? 'Datasets' : filesetLabel;
    const filesetCollectionLabelLower = filesetCollectionLabel.toLocaleLowerCase();
    if (isLoading) {
      return [
        { children: `Loading ${filesetCollectionLabelLower}...`, value: 'loading', disabled: true },
      ];
    } else if (isError) {
      return [
        {
          children: `Error loading ${filesetCollectionLabelLower}...`,
          value: 'error',
          disabled: true,
        },
      ];
    }

    return (
      filesets
        ?.sort((filesetA, filesetB) => (filesetA?.name || '').localeCompare(filesetB.name || ''))
        .map(filesetToOption) || []
    );
  }, [filesetLabel, filesets, isLoading, isError]);

  return (
    <FormField
      slotLabel={filesetLabel}
      slotError={
        <Flex gap="density-md" align="center">
          <CircleAlert className="text-feedback-danger" />
          <Text kind="label/regular/sm" className="text-feedback-danger">
            {error}
          </Text>
        </Flex>
      }
      status={error ? 'error' : undefined}
    >
      {(props) => (
        <Select
          {...props}
          aria-label={`${filesetLabel.toLocaleLowerCase()}-select`}
          className="motion-safe:[&.nv-input:not(.nv-input--disabled):not(.nv-input--readonly)]:transition-[margin,color,background-color,border-color,outline-color,text-decoration-color,fill,stroke] duration-250 data-[state=open]:mb-24"
          disabled={disabled}
          items={[
            ...(allowNewDataset
              ? [
                  {
                    slotHeading: 'Create Dataset',
                    attributes: {
                      MenuHeading: { className: 'hidden', 'aria-hidden': true },
                    },
                    items: [
                      {
                        children: 'New Dataset',
                        value: 'new',
                      },
                    ],
                  },
                ]
              : []),
            {
              slotHeading: `Existing ${filesetLabel === 'Dataset' ? 'Datasets' : filesetLabel}`,
              attributes: { MenuHeading: { className: 'hidden', 'aria-hidden': true } },
              items: datasetOptions,
            },
          ]}
          value={selectedDatasetOption}
          onValueChange={handleDatasetSelect}
          placeholder={`Select ${filesetLabel === 'Dataset' ? 'a dataset' : 'a fileset'}`}
        />
      )}
    </FormField>
  );
};
