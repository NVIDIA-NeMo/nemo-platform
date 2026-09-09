// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getErrorMessage } from '@nemo/common/src/api/common/utils';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Banner, Grid, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import {
  deleteCustomizationJobTemplate,
  getCustomizationJobTemplatesQueryKey,
  listCustomizationJobTemplates,
  templateToFormFields,
} from '@studio/api/customization-job-templates/customizationJobTemplates';
import {
  templateBadges,
  templateFooterLines,
  trainingLabelForFields,
} from '@studio/components/CreateCustomizationStart/templateBadges';
import { TemplateCard } from '@studio/components/CreateCustomizationStart/TemplateCard';
import type {
  TemplateCardModel,
  TemplateGridProps,
} from '@studio/components/CreateCustomizationStart/types';
import { CUSTOMIZATION_TEMPLATES } from '@studio/constants/customizationTemplates';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FC } from 'react';

const CURATED_CARDS: TemplateCardModel[] = CUSTOMIZATION_TEMPLATES.map((template) => ({
  key: `curated:${template.id}`,
  selection: { kind: 'curated', id: template.id },
  publisher: template.publisher,
  title: template.title,
  description: template.description,
  badges: templateBadges(template.backend, template.trainingLabel),
  footer: [
    `${template.stats.totalParams} params · ${template.stats.activeParams} active · ${template.stats.gpus} GPUs`,
  ],
  requiresHfToken: template.models.some((model) => model.requiresHfToken),
  applicable: true,
}));

export const TemplateGrid: FC<TemplateGridProps> = ({
  workspace,
  selectedTemplate,
  onSelectTemplate,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const {
    data: page,
    isPending,
    error,
  } = useQuery({
    queryKey: getCustomizationJobTemplatesQueryKey(workspace),
    queryFn: ({ signal }) => listCustomizationJobTemplates(workspace, undefined, signal),
  });

  const { mutate: remove } = useMutation({
    mutationFn: (name: string) => {
      setDeletingName(name);
      return deleteCustomizationJobTemplate(workspace, name);
    },
    onSuccess: (_result, name) => {
      void queryClient.invalidateQueries({
        queryKey: getCustomizationJobTemplatesQueryKey(workspace).slice(0, 2),
      });
      // Or Continue stays enabled pointing at something that no longer exists.
      if (selectedTemplate?.kind === 'saved' && selectedTemplate.name === name) {
        onSelectTemplate(null);
      }
      toast.success(`Deleted template '${name}'`);
    },
    onError: (e: Error) => toast.error(getErrorMessage(e, 'Failed to delete template')),
    onSettled: () => setDeletingName(null),
  });

  // User templates lead: they apply instantly, where recipes provision first.
  const savedCards: TemplateCardModel[] = (page?.data ?? []).map((template) => {
    const fields = templateToFormFields(template);
    return {
      key: `saved:${template.id}`,
      selection: { kind: 'saved', name: template.name },
      publisher: 'User created',
      title: template.name,
      description: template.data.description,
      badges: fields
        ? templateBadges(template.data.backend, trainingLabelForFields(fields))
        : templateBadges(template.data.backend, ''),
      footer: fields ? templateFooterLines(fields) : undefined,
      applicable: fields !== undefined,
      isDeleting: deletingName === template.name,
      onDelete: () => remove(template.name),
    };
  });

  const cards = [...savedCards, ...CURATED_CARDS];

  const isSelected = (card: TemplateCardModel) =>
    selectedTemplate !== null &&
    (card.selection.kind === 'saved'
      ? selectedTemplate.kind === 'saved' && selectedTemplate.name === card.selection.name
      : selectedTemplate.kind === 'curated' && selectedTemplate.id === card.selection.id);

  return (
    <Stack gap="density-md">
      {error ? (
        <Banner kind="inline" status="error">
          {`Failed to load your saved templates. ${getErrorMessage(error, 'Please try again.')}`}
        </Banner>
      ) : null}

      {isPending ? <Spinner size="small" aria-label="Loading your templates" /> : null}

      {/* Fixed three columns rather than an auto-fill min-width, so a short list keeps
          card-sized cards instead of stretching one across the whole row. */}
      <Grid cols={{ base: 1, md: 2, lg: 3 }} gap="density-md">
        {cards.map((card) => (
          <TemplateCard
            key={card.key}
            model={card}
            selected={isSelected(card)}
            onSelect={() => onSelectTemplate(card.selection)}
          />
        ))}
      </Grid>

      {!isPending && !error && savedCards.length === 0 ? (
        <Text kind="body/regular/sm" className="text-secondary">
          You haven&apos;t saved any templates yet. Configure a fine-tuning job, or open one you
          already ran, and choose &ldquo;Save as Template&rdquo; to reuse it later.
        </Text>
      ) : null}
    </Stack>
  );
};
