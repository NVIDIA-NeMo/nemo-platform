// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Canonical tab IDs for the Fileset Detail page.
 *
 * These string values appear as the SegmentedControl item `value` props and as
 * the `?tab=<id>` URL query value. Add a tab here, reference it everywhere.
 */
export enum FilesetDetailTab {
  Card = 'card',
  Files = 'files',
}

export const FILESET_DETAIL_DEFAULT_TAB = FilesetDetailTab.Card;

export const isFilesetDetailTab = (value: string | undefined): value is FilesetDetailTab =>
  Object.values(FilesetDetailTab).includes(value as FilesetDetailTab);
