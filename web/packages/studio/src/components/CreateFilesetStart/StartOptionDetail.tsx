// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Divider, Flex, Grid, Stack, Text } from '@nvidia/foundations-react-core';
import { TemplateCard } from '@studio/components/CreateFilesetStart/TemplateCard';
import { FILESET_TEMPLATES } from '@studio/components/CreateFilesetStart/templates';
import type {
  DetailPoint,
  StartOption,
  StartOptionDetailProps,
} from '@studio/components/CreateFilesetStart/types';
import { Layers, Sparkles, Wand2 } from 'lucide-react';
import type { FC, ReactNode } from 'react';

const SCRATCH_POINTS: DetailPoint[] = [
  {
    icon: Layers,
    title: 'Add columns block by block',
    description:
      'Drop in samplers, LLM generations, transforms and validators in any order on an empty canvas.',
  },
  {
    icon: Wand2,
    title: 'Wire columns together',
    description: 'Reference earlier columns in prompts and expressions to build up each record.',
  },
  {
    icon: Sparkles,
    title: 'Preview and run',
    description: 'Generate a sample at any time, tweak, and run the full job when it looks right.',
  },
];

const DETAIL_CONTENT: Partial<Record<StartOption['id'], ReactNode>> = {
  scratch: (
    <Flex gap="density-md" className="w-full flex-wrap">
      {SCRATCH_POINTS.map(({ icon: Icon, title, description }) => (
        <Stack
          key={title}
          gap="density-xs"
          className="min-w-[260px] flex-1 rounded-md border border-base bg-surface-raised p-5"
        >
          <Flex
            align="center"
            justify="center"
            className="size-8 shrink-0 rounded-md bg-surface-sunken"
          >
            <Icon size={16} className="text-primary" aria-hidden />
          </Flex>
          <Text kind="body/semibold/sm" className="text-primary">
            {title}
          </Text>
          <Text kind="body/regular/sm" className="text-secondary">
            {description}
          </Text>
        </Stack>
      ))}
    </Flex>
  ),
};

export const StartOptionDetail: FC<StartOptionDetailProps> = ({
  option,
  selectedTemplateId,
  onSelectTemplate,
}) => {
  const content =
    option.id === 'template' ? (
      <Grid colMinWidth="260px" gap="density-md">
        {FILESET_TEMPLATES.map((template) => (
          <TemplateCard
            key={template.id}
            template={template}
            selected={selectedTemplateId === template.id}
            onSelect={() => onSelectTemplate(template.id)}
          />
        ))}
      </Grid>
    ) : (
      DETAIL_CONTENT[option.id]
    );

  if (!content) {
    return null;
  }

  return (
    <Stack gap="density-md" className="w-full">
      <Divider />
      <Text kind="label/bold/sm" className="text-secondary">
        {option.title}
      </Text>
      {content}
    </Stack>
  );
};
