// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FileSystemNode } from '@studio/components/FilesTable/utils';

export const getItemId = (item: FileSystemNode) => [item.oid, item.type, item.path].join('-');
