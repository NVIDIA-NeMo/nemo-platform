// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { FC } from 'react';

const EXAMPLES: { template: string; description: string }[] = [
  { template: '{{{column}}}', description: 'Insert a source column verbatim.' },
  { template: '{{column}}', description: 'Same, but HTML-escapes the value.' },
  { template: '{{@row}}', description: 'The 1-based row number.' },
  { template: 'task-{{@row}}', description: 'Mix literal text with templates.' },
  { template: '{{#if a}}{{{a}}}{{else}}{{{b}}}{{/if}}', description: 'Fall back when a is empty.' },
  {
    template: '["{{{a}}}", "{{{b}}}"]',
    description: 'Output starting with [ or { is parsed as JSON.',
  },
];

/** Popover content for the mapping grid's value column. */
export const MappingValueHelp: FC = () => (
  <Stack gap="density-md">
    <Text>
      Values are Handlebars templates evaluated once per row. Anything outside the braces is copied
      through as literal text.
    </Text>
    <Stack gap="density-xs">
      {EXAMPLES.map(({ template, description }) => (
        <Text key={template}>
          <code>{template}</code> — {description}
        </Text>
      ))}
    </Stack>
  </Stack>
);
