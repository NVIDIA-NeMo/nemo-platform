// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Panel,
  Text,
} from '@nvidia/foundations-react-core';
import { Braces } from 'lucide-react';
import type { FC } from 'react';

/**
 * Collapsed raw-JSON escape hatch. Guarantees zero information loss and covers
 * any config field the structured view does not yet render.
 */
export const RawConfigSection: FC<{ data: RailsConfigOutput }> = ({ data }) => (
  <Panel slotHeading="Raw configuration" slotIcon={<Braces />} elevation="high" density="compact">
    <AccordionRoot>
      <AccordionItem value="raw-config">
        <AccordionTrigger>
          <Text kind="label/bold/sm">Show configuration JSON</Text>
        </AccordionTrigger>
        <AccordionContent>
          <pre className="overflow-auto rounded bg-surface-raised p-density-md text-xs leading-relaxed">
            {JSON.stringify(data, null, 2)}
          </pre>
        </AccordionContent>
      </AccordionItem>
    </AccordionRoot>
  </Panel>
);
