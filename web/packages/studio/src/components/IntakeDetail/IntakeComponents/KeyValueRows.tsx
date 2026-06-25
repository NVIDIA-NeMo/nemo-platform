// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import type { KeyValueEntry } from '@studio/components/IntakeDetail/IntakeComponents/keyValueTypes';
import type { FC } from 'react';

/** Full-width key/value rows for metadata sections (IDs, links, JSON, etc.). */
export const KeyValueRows: FC<{ entries: readonly KeyValueEntry[] }> = ({ entries }) => {
  if (entries.length === 0) {
    return null;
  }
  return (
    <Stack gap="density-sm" className="min-w-0">
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-start gap-density-md border-b border-base pb-density-sm last:border-b-0 last:pb-0 min-w-0"
        >
          <Text kind="label/regular/sm" className="w-[180px] shrink-0 text-secondary">
            {entry.label}
          </Text>
          <div className={`min-w-0 text-left ${entry.wrapValue ? 'break-all text-wrap' : ''}`}>
            {entry.value}
          </div>
        </div>
      ))}
    </Stack>
  );
};
