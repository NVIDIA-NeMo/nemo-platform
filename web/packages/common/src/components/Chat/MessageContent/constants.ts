// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { MarkdownTableOptions } from '@nemo/common/src/components/Chat/MessageContent/types';

export const INLINE_CODE_CLASS =
  'rounded bg-gray-050 px-1 py-0.5 font-sans text-sm dark:bg-gray-800';

export const DEFAULT_MARKDOWN_TABLE_OPTIONS: Required<MarkdownTableOptions> = {
  expandableCells: true,
};
