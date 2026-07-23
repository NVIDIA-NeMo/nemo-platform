// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';

export interface FilesetRef {
  workspace: string;
  name: string;
}

export const parseFilesetRef = (ref: string | null | undefined): FilesetRef | null => {
  if (!ref) return null;
  try {
    const url = new URL(ref);
    if (url.protocol !== 'fileset:' || !url.hostname) return null;
    const name = url.pathname.split('/').filter(Boolean)[0];
    return name ? { workspace: url.hostname, name } : null;
  } catch {
    return null;
  }
};

export const useArtifactText = (
  fileset: FilesetRef | null,
  path: string | null | undefined,
  enabled = true
) =>
  useDatasetFileContent({
    workspace: fileset?.workspace ?? '',
    name: fileset?.name ?? '',
    path: path ?? '',
    enabled: enabled && !!fileset && !!path,
  });

export const parseArtifactJson = <T,>(content: string | undefined): T | null => {
  if (!content) return null;
  try {
    return JSON.parse(content) as T;
  } catch {
    return null;
  }
};
