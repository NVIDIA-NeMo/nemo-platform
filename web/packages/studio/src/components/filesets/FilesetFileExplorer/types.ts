// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import type { FileSystemNode } from '@studio/components/FilesTable/utils';
import type { ReactNode } from 'react';

/**
 * Optional extra column injected by a consumer of FilesetFileExplorer.
 * Each extra column is appended after the built-in Name and Size columns
 * and rendered before the trailing quick-actions column.
 *
 * The cell renderer receives every FileSystemNode (files AND directories);
 * return null for nodes that should render nothing.
 */
export interface ExtraColumn {
  header: ReactNode;
  cell: (node: FileSystemNode) => ReactNode;
  /** Optional fixed header-cell width in px. */
  width?: number;
}

export interface FilesetFileExplorerProps {
  /** Dataset workspace */
  workspace: string;
  /** Dataset name */
  datasetName: string;
  /** Full dataset identifier (workspace/name) */
  datasetId: string;
  /** Current folder path (from query param or state) */
  currentFolder?: string;
  /** All files in the dataset (for navigation and search) */
  filesList: FilesetFileOutput[] | undefined;
  /** Whether file-list data is loading */
  isLoading: boolean;
  /** Whether files are currently being fetched */
  isFilesFetching: boolean;
  /** Callback when a file is selected for viewing. When omitted, file rows are
   *  non-interactive (no row-click navigation, no "View File" quick action).
   *  Hosts that don't yet have a preview surface should leave this undefined
   *  rather than passing a no-op, so the view affordance isn't exposed. */
  onFileSelect?: (filePath: string) => void;
  /** Gates the fileset metadata fetch. Defaults to true.
   *  Hosts that mount the explorer behind a panel animation can pass the panel's
   *  open state to suppress fetches while closed. */
  enabled?: boolean;
  /** Purpose-specific columns appended after Name + Size and before quick-actions.
   *  Hosts use this to inject domain columns (e.g. dataset Schema) without
   *  pushing dataset-specific knowledge into the shared explorer. */
  extraColumns?: ExtraColumn[];
  /** Fires when the user explicitly toggles a folder open or closed (row click).
   *  Does NOT fire for the explorer's own auto-expansion from `currentFolder`.
   *  Hosts can use this to sync URL state (e.g. drop `?filesetFolder=` when the
   *  user collapses the folder that was named in the URL). */
  onFolderToggle?: (folderPath: string, isExpanded: boolean) => void;
}
