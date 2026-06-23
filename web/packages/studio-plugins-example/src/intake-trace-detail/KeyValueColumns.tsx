// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { splitIntoEqualColumns } from '@nemo/studio-plugins-example/intake-trace-detail/splitIntoEqualColumns';
import type { KeyValueEntry } from '@nemo/studio-plugins-example/intake-trace-detail/keyValueTypes';
import { KVPair } from '@nemo/common/src/components/KVPair';
import { Grid, Stack } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

const COLUMN_COUNT = 3;

interface KeyValueColumnsProps {
  entries: readonly KeyValueEntry[];
}

/** Renders key-value rows in three columns using horizontal KUI KVPair layout. */
export const KeyValueColumns: FC<KeyValueColumnsProps> = ({ entries }) => {
  const columns = splitIntoEqualColumns(entries, COLUMN_COUNT);

  if (entries.length === 0) {
    return null;
  }

  return (
    <Grid className="grid-cols-1 md:grid-cols-3 gap-density-xl">
      {columns.map((columnEntries, columnIndex) => (
        <Stack key={`kv-column-${columnIndex}`} gap="density-lg" className="min-w-0">
          {columnEntries.map((entry) => (
            <KVPair
              key={entry.id}
              label={entry.label}
              value={entry.value}
              orientation="horizontal"
              attributes={
                entry.wrapValue
                  ? {
                      value: {
                        className: 'min-w-0 break-all text-wrap',
                      },
                    }
                  : undefined
              }
            />
          ))}
        </Stack>
      ))}
    </Grid>
  );
};
