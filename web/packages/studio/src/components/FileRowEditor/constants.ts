// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TagProps } from '@nvidia/foundations-react-core';
import type { DataFileFormat } from '@studio/components/FileRowEditor/parse';
import type { DataFileColumnType } from '@studio/components/FileRowEditor/types';

type TagColor = NonNullable<TagProps['color']>;

/** Column data type → Tag color used for the schema chips in the editor and table. */
export const COLUMN_TYPE_TAG_COLOR: Record<DataFileColumnType, TagColor> = {
  int: 'blue',
  float: 'blue',
  string: 'gray',
  boolean: 'green',
  json: 'purple',
  null: 'gray',
};

/** File format → Tag color for the header chip. */
export const FILE_FORMAT_TAG_COLOR: Record<DataFileFormat, TagColor> = {
  json: 'purple',
  jsonl: 'purple',
  csv: 'blue',
  parquet: 'green',
  unknown: 'gray',
};
