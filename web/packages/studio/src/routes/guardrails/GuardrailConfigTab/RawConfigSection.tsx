// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { Braces } from 'lucide-react';
import { type FC, useMemo } from 'react';

/**
 * Grows with the document between bounds, so a new guardrail isn't a mostly-empty box and
 * a large config doesn't take over the page. Matches the sizing other editors in Studio use.
 */
const EDITOR_CLASS = 'min-h-[200px] max-h-[560px]';

/**
 * The complete guardrail document, as it will be saved.
 *
 * Shown rather than hidden behind a disclosure: it is the only view of the fields Studio
 * cannot configure yet, and the only way to see what switching a rail on actually wrote.
 */
export const RawConfigSection: FC<{ data: RailsConfig }> = ({ data }) => {
  const json = useMemo(() => JSON.stringify(data, null, 2), [data]);

  return (
    <Panel
      slotHeading="Configuration JSON"
      slotIcon={<Braces />}
      elevation="high"
      density="compact"
    >
      <Stack gap="density-sm">
        <Text kind="body/regular/sm" className="text-text-secondary">
          The full configuration, including any settings this page does not surface. Read-only.
        </Text>
        <CodeEditor
          className={EDITOR_CLASS}
          content={json}
          readOnly
          contentType={ContentType.JSON}
        />
      </Stack>
    </Panel>
  );
};
