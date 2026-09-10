// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Grid, Stack } from '@nvidia/foundations-react-core';
import { TemplateCard } from '@studio/components/CreateCustomizationStart/TemplateCard';
import type {
  TemplateCardModel,
  TemplateGridProps,
} from '@studio/components/CreateCustomizationStart/types';
import { CUSTOMIZATION_TEMPLATES } from '@studio/constants/customizationTemplates';
import type { FC } from 'react';

const CARDS: TemplateCardModel[] = CUSTOMIZATION_TEMPLATES.map((template) => ({
  key: template.id,
  selection: { kind: 'curated', id: template.id },
  publisher: template.publisher,
  title: template.title,
  description: template.description,
  badges: [{ label: template.trainingLabel, color: 'gray' }],
  footer: [
    `${template.stats.totalParams} params · ${template.stats.activeParams} active · ${template.stats.gpus} GPUs`,
  ],
  requiresHfToken: template.models.some((model) => model.requiresHfToken),
  applicable: true,
}));

export const TemplateGrid: FC<TemplateGridProps> = ({ selectedTemplate, onSelectTemplate }) => (
  <Stack gap="density-md">
    {/* Fixed columns rather than an auto-fill min-width, so a short list keeps card-sized
        cards instead of stretching one across the whole row. */}
    <Grid cols={{ base: 1, md: 2, lg: 3 }} gap="density-md">
      {CARDS.map((card) => (
        <TemplateCard
          key={card.key}
          model={card}
          selected={selectedTemplate?.id === card.selection.id}
          onSelect={() => onSelectTemplate(card.selection)}
        />
      ))}
    </Grid>
  </Stack>
);
