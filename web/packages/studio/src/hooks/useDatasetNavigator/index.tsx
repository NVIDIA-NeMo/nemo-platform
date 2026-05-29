// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import {
  getFoldersFilesAtPath,
  mapFileListToFileTree,
  toFileEntry,
} from '@studio/components/FilesTable/utils';
import { useMemo } from 'react';

export function useDatasetNavigator(
  filesList: FilesetFileOutput[] | undefined,
  currentFolder: string
) {
  const fileTree = useMemo(() => {
    if (!filesList) return mapFileListToFileTree([]);
    const entries = filesList.map(toFileEntry);
    return mapFileListToFileTree(entries);
  }, [filesList]);
  const { entries } = useMemo(
    () => getFoldersFilesAtPath(fileTree, currentFolder),
    [fileTree, currentFolder]
  );
  return entries;
}
