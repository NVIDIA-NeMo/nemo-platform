// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  Flex,
  Modal,
  SelectContent,
  SelectItem,
  SelectRoot,
  SelectTrigger,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { collectFolderPathsFromDatasetFiles } from '@studio/util/files';
import { FolderClosed, Upload } from 'lucide-react';
import { FC, useEffect, useMemo, useRef, useState } from 'react';

const ROOT_VALUE = '__root__';

const normalizeFolderOption = (folder: string | undefined): string => {
  if (!folder?.trim()) return ROOT_VALUE;
  const t = folder.trim();
  return t.endsWith('/') ? t.slice(0, -1) : t;
};

export interface UploadToFolderModalProps {
  open: boolean;
  onClose: () => void;
  /** Files to upload (may be empty until user picks files via Browse) */
  files: File[];
  /** Default folder path from breadcrumbs (without trailing slash) */
  defaultFolder?: string;
  filesList: FilesetFileOutput[] | undefined;
  /** Called with files and folder path (undefined = dataset root) */
  onConfirm: (files: File[], destinationFolder: string | undefined) => void | Promise<void>;
  /** Opens the native file picker (from dropzone) */
  openFileDialog: () => void;
}

/**
 * Lets the user choose which folder files are uploaded into before starting the upload.
 */
export const UploadToFolderModal: FC<UploadToFolderModalProps> = ({
  open,
  onClose,
  files,
  defaultFolder,
  filesList,
  onConfirm,
  openFileDialog,
}) => {
  const folderOptions = useMemo(() => collectFolderPathsFromDatasetFiles(filesList), [filesList]);
  const [selectedFolder, setSelectedFolder] = useState<string>(ROOT_VALUE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submitLockRef = useRef(false);

  useEffect(() => {
    if (open) {
      setSelectedFolder(normalizeFolderOption(defaultFolder));
    } else {
      setIsSubmitting(false);
      submitLockRef.current = false;
    }
  }, [open, defaultFolder]);

  const destinationLabel = selectedFolder === ROOT_VALUE ? 'dataset root' : `${selectedFolder}/`;

  const handleConfirm = async () => {
    if (files.length === 0 || submitLockRef.current) return;
    const folder = selectedFolder === ROOT_VALUE ? undefined : selectedFolder;
    submitLockRef.current = true;
    setIsSubmitting(true);
    try {
      await onConfirm(files, folder);
    } finally {
      submitLockRef.current = false;
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      slotHeading={
        <>
          <Upload />
          Upload files
        </>
      }
      slotFooter={
        <Flex justify="end" gap="density-xs" align="center" className="w-full">
          <Button kind="tertiary" color="neutral" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <LoadingButton
            onClick={handleConfirm}
            disabled={files.length === 0}
            loading={isSubmitting}
          >
            Upload
          </LoadingButton>
        </Flex>
      }
    >
      <Stack gap="density-md">
        <Text kind="body/regular/md">
          Choose where to upload{' '}
          {files.length > 0 ? `${files.length} file${files.length !== 1 ? 's' : ''}` : 'your files'}{' '}
          (destination: {destinationLabel}).
        </Text>
        <Flex direction="col" gap="density-xs" align="stretch">
          <Text kind="label/bold/sm">Destination folder</Text>
          <SelectRoot
            value={selectedFolder}
            onValueChange={setSelectedFolder}
            disabled={isSubmitting}
          >
            <SelectTrigger
              placeholder="Select folder"
              aria-label="Upload destination folder"
              slotStart={<FolderClosed className="size-4 shrink-0" />}
            />
            <SelectContent>
              <SelectItem value={ROOT_VALUE}>Root</SelectItem>
              {folderOptions.map((path) => (
                <SelectItem key={path} value={path}>
                  {path}
                </SelectItem>
              ))}
            </SelectContent>
          </SelectRoot>
        </Flex>
        <Flex gap="density-sm" align="center" wrap="wrap">
          <Button kind="secondary" type="button" onClick={openFileDialog} disabled={isSubmitting}>
            Select files…
          </Button>
          {files.length > 0 && (
            <Text kind="body/regular/sm" className="text-muted-foreground">
              {files.map((f) => f.name).join(', ')}
            </Text>
          )}
        </Flex>
      </Stack>
    </Modal>
  );
};
