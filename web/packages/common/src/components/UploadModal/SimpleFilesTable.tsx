// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import * as DataView from '@nemo/common/src/components/DataView/internal';
import { useUploadModalContext } from '@nemo/common/src/components/UploadModal/Context/useUploadModalContext';
import { useInlinePickerSlot } from '@nemo/common/src/components/UploadModal/InlinePickerSlot';
import { UploadFile } from '@nemo/common/src/components/UploadModal/types';
import { formatFileSize } from '@nemo/common/src/components/UploadModal/utils';
import {
  Button,
  Checkbox,
  Flex,
  RadioGroupInput,
  RadioGroupItem,
  RadioGroupRoot,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { CircleAlert } from 'lucide-react';
import { type ComponentProps, useCallback, useMemo, useRef } from 'react';

type FileRow = {
  id: string;
  name: string;
  size: number;
  isDisabled: boolean;
  uploadFile: UploadFile;
};

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

  const visibleFiles = useMemo(() => {
    if (invalidFileMode !== 'hide' || allowedExtensions.size === 0) return files;
    return files.filter(isFileAllowed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files, allowedExtensions, invalidFileMode]);

  const hasValidSelection = selectedFiles.some((file) => isFileAllowed(file));
  const disabledFilesMessage =
    invalidFileMode === 'disable' &&
    allowedExtensions.size > 0 &&
    !hasValidSelection &&
    visibleFiles.some((file) => !isFileAllowed(file))
      ? `Only ${acceptableFileTypes.join(', ')} files can be selected. Upload a supported file or choose a different fileset.`
      : null;

  const fileRows = useMemo<FileRow[]>(
    () =>
      visibleFiles.map((uploadFile) => {
        const isDisabled = invalidFileMode === 'disable' && !isFileAllowed(uploadFile);
        const name = uploadFile.type === 'existing' ? uploadFile.file.path : uploadFile.file.name;
        const size = uploadFile.type === 'existing' ? uploadFile.file.size : uploadFile.file.size;
        return { id: uploadFile.id, name, size, isDisabled, uploadFile };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visibleFiles, invalidFileMode, allowedExtensions]
  );

  const dataViewState = DataView.useDataViewState();

  const makeColumns = useCallback<ComponentProps<typeof DataView.Root<FileRow>>['makeColumns']>(
    (col) => [
      col.display({
        id: 'select',
        header: () => null,
        size: 40,
        maxSize: 40,
        minSize: 40,
        meta: { alignment: 'center' as const },
        cell: ({ row }) =>
          allowMultipleFileSelection ? (
            <Checkbox
              checked={selectedFiles.some((f) => f.id === row.original.id)}
              onCheckedChange={() =>
                dispatch({ type: 'TOGGLE_FILE_SELECTION', payload: row.original.uploadFile })
              }
              disabled={row.original.isDisabled}
              attributes={{ CheckboxInput: { 'aria-label': row.original.name } }}
            />
          ) : (
            <RadioGroupItem aria-label={row.original.name}>
              <RadioGroupInput value={row.original.id} disabled={row.original.isDisabled} />
            </RadioGroupItem>
          ),
      }),
      col.accessor('name', { header: 'Name' }),
      col.accessor('size', {
        header: 'Size',
        size: 120,
        cell: (ctx) => formatFileSize(ctx.getValue()),
      }),
    ],
    [allowMultipleFileSelection, selectedFiles, dispatch]
  );

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newFiles = event.target.files;
    if (newFiles) {
      dispatch({
        type: 'SET_FILES',
        payload: Array.from(newFiles).map((file) => ({ id: file.name, type: 'new', file })),
      });
    }
  };

  return (
    <Stack className="min-h-0 flex-1 w-full" gap="density-md">
      {/* Name column fills the row; Size (col 3) is pinned to 120px. */}
      <div className="border border-base rounded-md overflow-hidden [&_tr>*:nth-child(2)]:w-full! [&_tr>*:nth-child(2)]:max-w-none! [&_tr>*:nth-child(3)]:w-[120px]! [&_tr>*:nth-child(3)]:min-w-[120px]! [&_tr>*:nth-child(3)]:max-w-[120px]!">
        <RadioGroupRoot
          name="simple-files-table"
          value={selectedFiles[0]?.id ?? ''}
          onValueChange={(id) => {
            const file = fileRows.find((r) => r.id === id);
            if (file) dispatch({ type: 'TOGGLE_FILE_SELECTION', payload: file.uploadFile });
          }}
        >
          <DataView.Root
            data={fileRows}
            state={dataViewState}
            makeColumns={makeColumns}
            reactTableOptions={{ getRowId: (row) => row.id }}
          >
            <DataView.VirtualizedTableContent maxHeight="45dvh" />
          </DataView.Root>
        </RadioGroupRoot>
      </div>
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
