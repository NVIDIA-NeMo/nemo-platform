// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Accordion, Flex, Text } from '@nvidia/foundations-react-core';
import { ConfigPreview } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/ConfigPreview';
import { SearchSpaceFields } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/SearchSpaceFields';
import {
  formatRange,
  type SearchParameter,
} from '@studio/routes/agents/AgentDetailRoute/optimizations/optimizeConfig';
import { OPTIMIZE_CONFIG_PATH } from '@studio/routes/agents/AgentDetailRoute/optimizations/submitOptimization';
import { type FC, type ReactNode } from 'react';

/** Collapsed summary line: enough to see the search space without opening the panel. */
const summarize = (parameters: SearchParameter[]): string =>
  [
    ...parameters.map((parameter) => `${parameter.label} ${formatRange(parameter)}`),
    `${parameters.length} parameter${parameters.length === 1 ? '' : 's'}`,
  ].join(' · ');

const trigger = (label: string, hint: ReactNode) => (
  <Flex align="center" gap="density-md" wrap="wrap">
    <Text kind="body/semibold/sm">{label}</Text>
    <Text kind="body/regular/xs" color="secondary">
      {hint}
    </Text>
  </Flex>
);

export interface AdvancedAccordionProps {
  searchSpace: SearchParameter[];
  config: string;
}

/**
 * The two escape hatches from the guided form, in one accordion.
 *
 * Both are the same kind of thing — the machinery the three steps above generate — so they sit
 * together and open one at a time: reading the YAML is how you check what the search-space fields
 * did, and there is no reason to look at both at once.
 */
export const AdvancedAccordion: FC<AdvancedAccordionProps> = ({ searchSpace, config }) => (
  <Accordion
    multiple
    items={[
      {
        value: 'search-space',
        chevronPosition: 'start',
        slotTrigger: trigger('Advanced — edit the search space', summarize(searchSpace)),
        slotContent: <SearchSpaceFields />,
      },
      {
        value: 'config',
        chevronPosition: 'start',
        slotTrigger: trigger(OPTIMIZE_CONFIG_PATH, 'generated from your answers'),
        slotContent: <ConfigPreview config={config} />,
      },
    ]}
  />
);
