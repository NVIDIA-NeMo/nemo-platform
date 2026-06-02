// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import type { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Divider, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { getMetadataSections } from '@studio/routes/ModelDetailRoute/ModelMetadataPanel/utils';
import { type FC } from 'react';

export interface ModelMetadataPanelProps {
  fileset: FilesetOutput;
  readmeMetadata?: Record<string, unknown>;
}

export const ModelMetadataPanel: FC<ModelMetadataPanelProps> = ({ fileset, readmeMetadata }) => {
  const sections = getMetadataSections(fileset, readmeMetadata);

  return (
    <Panel elevation="high" density="compact" className="w-full" data-testid="model-metadata-panel">
      <Stack gap="density-xl">
        {sections.map((section, index) => (
          <Stack key={section.value} gap="density-lg">
            {index > 0 ? <Divider /> : null}
            <Text kind="label/bold/sm">{section.title}</Text>
            <Stack gap="density-md">
              {section.rows.map((row) => (
                <KVPair
                  key={`${section.value}-${row.label}`}
                  label={row.label}
                  value={row.value}
                  orientation="horizontal"
                  size="narrow"
                  attributes={{
                    value: { className: 'min-w-0 break-words text-wrap' },
                  }}
                />
              ))}
            </Stack>
          </Stack>
        ))}
      </Stack>
    </Panel>
  );
};
