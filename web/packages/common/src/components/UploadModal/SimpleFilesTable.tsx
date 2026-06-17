// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ScrollTable } from '@nemo/common/src/components/ScrollTable';
import { useUploadModalContext } from '@nemo/common/src/components/UploadModal/Context/useUploadModalContext';
import { useInlinePickerSlot } from '@nemo/common/src/components/UploadModal/InlinePickerSlot';
import { UploadFile } from '@nemo/common/src/components/UploadModal/types';
import { formatFileSize } from '@nemo/common/src/components/UploadModal/utils';
import {
  Button,
  Checkbox,
  Text,
  TableColumnDefinition,
  TableRowDefinition,
  Flex,
  Stack,
  RadioGroupRoot,
  RadioGroupItem,
  RadioGroupInput,
} from '@nvidia/foundations-react-core';
import { CircleAlert } from 'lucide-react';
import { useCallback, useMemo } from 'react';

export const SimpleFilesTable = () => {
  const [state, dispatch] = useUploadModalContext();
  const { trailingButton } = useInlinePickerSlot();
  const {
    files,
    selectedFiles,
    errors,
    acceptableFileTypes,
    allowMultipleFileSelection,
    invalidFileMode,
  } = state;

  const fileExtension = (uploadFile: UploadFile): string => {
    const name = uploadFile.type === 'existing' ? uploadFile.file.path : uploadFile.file.name;
    const dot = name.lastIndexOf('.');
    return dot >= 0 ? name.slice(dot).toLowerCase() : '';
  };

  const allowedExtensions = useMemo(
    () => new Set((acceptableFileTypes ?? []).map((ext) => ext.toLowerCase())),
    [acceptableFileTypes]
  );

  const isFileAllowed = (uploadFile: UploadFile): boolean => {
    if (allowedExtensions.size === 0) return true;
    return allowedExtensions.has(fileExtension(uploadFile));
  };
  const toggleFileSelection = useCallback(
    (file: UploadFile) => {
      dispatch({
        type: 'TOGGLE_FILE_SELECTION',
        payload: file,
      });
    },
    [dispatch]
  );
  const handleSingleSelect = useCallback(
    (id: string) => {
      const file = files.find((f) => f.id === id);
      if (!file) return;
      dispatch({ type: 'TOGGLE_FILE_SELECTION', payload: file });
    },
    [dispatch, files]
  );
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files) {
      dispatch({
        type: 'SET_FILES',
        payload: Array.from(files).map((file) => ({ id: file.name, type: 'new', file })),
      });
    }
  };

  const columns: TableColumnDefinition[] = [
    { children: '' },
    { children: 'Name' },
    { children: 'Size' },
  ];

  // ``invalidFileMode`` controls how files whose extension isn't in
  // ``acceptableFileTypes`` are rendered. ``'hide'`` filters them out so the
  // user only sees pickable files; ``'disable'`` keeps them visible but
  // marks the radio/checkbox as ``disabled``; ``'show'`` (default) keeps
  // the prior behaviour and lets the parent validate after submit.
  const visibleFiles = useMemo(() => {
    if (invalidFileMode !== 'hide' || allowedExtensions.size === 0) return files;
    return files.filter(isFileAllowed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files, allowedExtensions, invalidFileMode]);

  const disabledFilesMessage =
    invalidFileMode === 'disable' &&
    allowedExtensions.size > 0 &&
    visibleFiles.some((file) => !isFileAllowed(file))
      ? `Only ${acceptableFileTypes.join(', ')} files can be selected. Upload a supported file or choose a different fileset.`
      : null;

  const rows = useMemo<TableRowDefinition[]>(
    () =>
      visibleFiles.map((uploadFile) => {
        // In ``'disable'`` mode, mismatched-extension rows render but their
        // selector control is ``disabled``. ``'hide'`` already filtered
        // them; ``'show'`` keeps everything pickable.
        const isDisabled = invalidFileMode === 'disable' && !isFileAllowed(uploadFile);
        const name = uploadFile.type === 'existing' ? uploadFile.file.path : uploadFile.file.name;
        const size = uploadFile.type === 'existing' ? uploadFile.file.size : uploadFile.file.size;
        return {
          id: uploadFile.id,
          cells: [
            {
              children: allowMultipleFileSelection ? (
                <Checkbox
                  name={name}
                  attributes={{ CheckboxInput: { 'aria-label': name } }}
                  checked={selectedFiles.some((file) => file.id === uploadFile.id)}
                  onCheckedChange={() => toggleFileSelection(uploadFile)}
                  disabled={isDisabled}
                />
              ) : (
                <RadioGroupItem aria-label={name}>
                  <RadioGroupInput value={uploadFile.id} disabled={isDisabled} />
                </RadioGroupItem>
              ),
            },
            { children: name },
            { children: formatFileSize(size) },
          ],
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visibleFiles, selectedFiles, toggleFileSelection, allowMultipleFileSelection, invalidFileMode]
  );

  return (
    <Stack className="min-h-0 flex-1 w-full" gap="density-md">
      {allowMultipleFileSelection ? (
        <ScrollTable
          pagination={false}
          columns={columns}
          rows={rows}
          allowHorizontalScroll
          className="pb-0 w-full"
        />
      ) : (
        // ``RadioGroupRoot`` defaults to its content's natural width — force
        // ``w-full`` so the inner ScrollTable fills the modal's width.
        <RadioGroupRoot
          name="simple-files-table"
          value={selectedFiles[0]?.id ?? ''}
          onValueChange={handleSingleSelect}
          className="w-full"
        >
          <ScrollTable
            pagination={false}
            columns={columns}
            rows={rows}
            allowHorizontalScroll
            className="pb-0 w-full"
          />
        </RadioGroupRoot>
      )}
      {disabledFilesMessage ? (
        <Flex gap="density-sm" align="center">
          <CircleAlert className="text-feedback-warning shrink-0" />
          <Text kind="label/regular/sm" className="text-feedback-warning">
            {disabledFilesMessage}
          </Text>
        </Flex>
      ) : null}
      {errors.file && (
        <Flex gap="density-md" align="center">
          <CircleAlert className="text-feedback-danger" />
          <Text kind="label/regular/sm" className="text-feedback-danger">
            {errors.file}
          </Text>
        </Flex>
      )}
      {trailingButton ? (
        <Flex justify="between" align="center">
          <Button kind="tertiary" asChild>
            <label htmlFor="upload-more-files">Upload More Files</label>
          </Button>
          {trailingButton}
        </Flex>
      ) : (
        <Button kind="tertiary" asChild>
          <label htmlFor="upload-more-files">Upload More Files</label>
        </Button>
      )}
      <input
        id="upload-more-files"
        type="file"
        multiple
        onChange={handleFileChange}
        accept={acceptableFileTypes.join(',')}
        className="sr-only"
      />
    </Stack>
  );
};
