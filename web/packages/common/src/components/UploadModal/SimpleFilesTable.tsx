// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useUploadModalContext } from '@nemo/common/src/components/UploadModal/Context/useUploadModalContext';
import { useInlinePickerSlot } from '@nemo/common/src/components/UploadModal/InlinePickerSlot';
import { UploadFile } from '@nemo/common/src/components/UploadModal/types';
import { formatFileSize } from '@nemo/common/src/components/UploadModal/utils';
import {
  Button,
  Checkbox,
  Text,
  Flex,
  Stack,
  RadioGroupRoot,
  RadioGroupItem,
  RadioGroupInput,
  TableBody,
  TableDataCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from '@nvidia/foundations-react-core';
import { CircleAlert } from 'lucide-react';
import { useCallback, useMemo, useRef } from 'react';

export const SimpleFilesTable = () => {
  const [state, dispatch] = useUploadModalContext();
  const { trailingButton } = useInlinePickerSlot();
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const fileRows = useMemo(
    () =>
      visibleFiles.map((uploadFile) => {
        // In ``'disable'`` mode, mismatched-extension rows render but their
        // selector control is ``disabled``. ``'hide'`` already filtered
        // them; ``'show'`` keeps everything pickable.
        const isDisabled = invalidFileMode === 'disable' && !isFileAllowed(uploadFile);
        const name = uploadFile.type === 'existing' ? uploadFile.file.path : uploadFile.file.name;
        const size = uploadFile.type === 'existing' ? uploadFile.file.size : uploadFile.file.size;
        return { id: uploadFile.id, name, size, isDisabled, uploadFile };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visibleFiles, invalidFileMode, allowedExtensions]
  );

  const table = (
    <div className="overflow-y-auto max-h-[45dvh] border border-base rounded-md">
      <TableRoot layout="auto" align="left" className="w-full bg-inherit">
        <TableHead className="sticky top-0 z-[1] bg-surface-overlay border-b-0 sticky-table-header">
          <TableRow className="border-b-0">
            <TableHeaderCell />
            <TableHeaderCell>Name</TableHeaderCell>
            <TableHeaderCell>Size</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {fileRows.map(({ id, name, size, isDisabled, uploadFile }) => (
            <TableRow key={id}>
              <TableDataCell>
                {allowMultipleFileSelection ? (
                  <Checkbox
                    name={name}
                    attributes={{ CheckboxInput: { 'aria-label': name } }}
                    checked={selectedFiles.some((f) => f.id === id)}
                    onCheckedChange={() => toggleFileSelection(uploadFile)}
                    disabled={isDisabled}
                  />
                ) : (
                  <RadioGroupItem aria-label={name}>
                    <RadioGroupInput value={id} disabled={isDisabled} />
                  </RadioGroupItem>
                )}
              </TableDataCell>
              <TableDataCell>{name}</TableDataCell>
              <TableDataCell>{formatFileSize(size)}</TableDataCell>
            </TableRow>
          ))}
        </TableBody>
      </TableRoot>
    </div>
  );

  return (
    <Stack className="min-h-0 flex-1 w-full" gap="density-md">
      {allowMultipleFileSelection ? (
        table
      ) : (
        // ``RadioGroupRoot`` defaults to its content's natural width — force
        // ``w-full`` so the inner table fills the modal's width.
        <RadioGroupRoot
          name="simple-files-table"
          value={selectedFiles[0]?.id ?? ''}
          onValueChange={handleSingleSelect}
          className="w-full"
        >
          {table}
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
          <Button
            kind="tertiary"
            onClick={() => {
              fileInputRef.current?.click();
            }}
          >
            Upload More Files
          </Button>
          {trailingButton}
        </Flex>
      ) : (
        <Button
          kind="tertiary"
          onClick={() => {
            fileInputRef.current?.click();
          }}
        >
          Upload More Files
        </Button>
      )}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        tabIndex={-1}
        onChange={handleFileChange}
        accept={acceptableFileTypes.join(',')}
        className="sr-only"
        aria-label="Upload more files"
      />
    </Stack>
  );
};
