// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Divider, Flex, Grid, Stack, Text } from '@nvidia/foundations-react-core';
import { TemplateCard } from '@studio/components/CreateFilesetStart/TemplateCard';
import {
  FILESET_TEMPLATES,
  templateRequiresLlm,
} from '@studio/components/CreateFilesetStart/templates';
import type {
  DetailPoint,
  StartOption,
  StartOptionDetailProps,
} from '@studio/components/CreateFilesetStart/types';
import { Layers, Sparkles, Wand2 } from 'lucide-react';
import type { FC, ReactNode } from 'react';
import { Link } from 'react-router-dom';

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
  llmDisabled,
  inferenceProvidersHref,
}) => {
  // Show the provider error label only when a card is actually disabled by it.
  const hasDisabledTemplate =
    option.id === 'template' && llmDisabled && FILESET_TEMPLATES.some(templateRequiresLlm);

  const content =
    option.id === 'template' ? (
      <Grid colMinWidth="300px" gap="density-md">
        {FILESET_TEMPLATES.map((template) => (
          <TemplateCard
            key={template.id}
            template={template}
            selected={selectedTemplateId === template.id}
            disabled={llmDisabled && templateRequiresLlm(template)}
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
      {hasDisabledTemplate ? (
        <Banner status="warning" kind="inline">
          Templates that generate data with a model are disabled — this workspace has no NVIDIA
          Build inference provider.{' '}
          <Link to={inferenceProvidersHref} className="underline">
            Add the NVIDIA Build provider
          </Link>{' '}
          to enable them.
        </Banner>
      ) : null}
    </Stack>
  );
};
