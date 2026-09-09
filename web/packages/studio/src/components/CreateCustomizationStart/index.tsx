// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getErrorMessage } from '@nemo/common/src/api/common/utils';
import { toError } from '@nemo/common/src/utils/logger';
import {
  Banner,
  Block,
  Button,
  Flex,
  Grid,
  GridItem,
  PageHeader,
  Spinner,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import {
  getCustomizationJobTemplate,
  templateToFormFields,
} from '@studio/api/customization-job-templates/customizationJobTemplates';
import { START_OPTIONS } from '@studio/components/CreateCustomizationStart/constants';
import { StartOptionDetail } from '@studio/components/CreateCustomizationStart/StartOptionDetail';
import type {
  CreateCustomizationStartProps,
  StartOptionId,
  TemplateSelection,
} from '@studio/components/CreateCustomizationStart/types';
import { useTemplateSetup } from '@studio/components/CreateCustomizationStart/useTemplateSetup';
import { StartOptionCard } from '@studio/components/StartOptions/StartOptionCard';
import { CUSTOMIZATION_TEMPLATES } from '@studio/constants/customizationTemplates';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { ArrowRight } from 'lucide-react';
import { useCallback, useState, type FC } from 'react';

/** Why Continue is unavailable, shown next to the disabled button. */
const BLOCKED_HINT: Partial<Record<StartOptionId, string>> = {
  template: 'Pick a recipe to continue.',
  json: 'Paste or upload a valid config to continue.',
};

export const CreateCustomizationStart: FC<CreateCustomizationStartProps> = ({
  workspace,
  onContinue,
}) => {
  const [selectedId, setSelectedId] = useState<StartOptionId | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateSelection | null>(null);
  // Set only once a pasted config parses and validates, so Continue can never load a
  // config the form would immediately reject.
  const [jsonFields, setJsonFields] = useState<CustomizationFormFields | null>(null);

  const [savedTemplateError, setSavedTemplateError] = useState<string | null>(null);
  const [isLoadingSaved, setIsLoadingSaved] = useState(false);

  const { run: runTemplateSetup, statusLabel, error: templateError } = useTemplateSetup(workspace);
  const isSettingUp = statusLabel !== '' || isLoadingSaved;

  const selectedOption = START_OPTIONS.find((option) => option.id === selectedId) ?? null;

  const selectOption = (optionId: StartOptionId) => {
    setSelectedId(optionId);
    setSelectedTemplate(null);
    setJsonFields(null);
    setSavedTemplateError(null);
  };

  // Identity-stable so it can be a dependency of the JSON panel's validate callback.
  const handleValidConfig = useCallback(
    (fields: CustomizationFormFields | null) => setJsonFields(fields),
    []
  );

  // Ready to continue once a tile is chosen — plus that option's own payload: a template
  // card for "template", a config that parsed for "json".
  const canContinue =
    selectedOption !== null &&
    !isSettingUp &&
    (selectedOption.id !== 'template' || selectedTemplate !== null) &&
    (selectedOption.id !== 'json' || jsonFields !== null);

  const handleContinue = async () => {
    if (!selectedOption) return;
    if (selectedOption.id === 'scratch') {
      onContinue({ optionId: 'scratch' });
      return;
    }
    if (selectedOption.id === 'json' && jsonFields) {
      onContinue({ optionId: 'json', initialValues: jsonFields });
      return;
    }
    if (selectedOption.id !== 'template' || !selectedTemplate) return;

    if (selectedTemplate.kind === 'saved') {
      // Re-read the entity rather than trusting the list payload, so a template edited
      // in another tab since this page loaded applies as it is now.
      setSavedTemplateError(null);
      setIsLoadingSaved(true);
      try {
        const entity = await getCustomizationJobTemplate(workspace, selectedTemplate.name);
        const initialValues = templateToFormFields(entity);
        if (!initialValues) {
          setSavedTemplateError(
            'This template could not be applied — its saved settings are unreadable.'
          );
          return;
        }
        onContinue({ optionId: 'template', initialValues });
      } catch (e) {
        setSavedTemplateError(getErrorMessage(toError(e), 'Failed to load template'));
      } finally {
        setIsLoadingSaved(false);
      }
      return;
    }

    const template = CUSTOMIZATION_TEMPLATES.find((t) => t.id === selectedTemplate.id);
    if (!template) return;
    // Registering the model and loading the dataset has to finish before the form can
    // reference them, so it happens here rather than on the next screen.
    const initialValues = await runTemplateSetup(template);
    if (initialValues) onContinue({ optionId: 'template', initialValues });
  };

  return (
    <Stack className="h-full">
      <Block className="flex-1 overflow-auto">
        <Stack gap="density-2xl" padding="density-2xl">
          <PageHeader
            slotHeading="Fine-tune a Model"
            slotDescription="Train a model on your own data. Start from a config you already have, pick a ready-made recipe, or set everything up yourself."
          />

          <Stack gap="density-md">
            <Text kind="label/bold/sm" className="text-secondary">
              How do you want to start?
            </Text>
            <Grid colMinWidth="200px" gap="density-md">
              {START_OPTIONS.map((option) => (
                <GridItem key={option.id}>
                  <StartOptionCard
                    compact
                    option={option}
                    selected={selectedId === option.id}
                    onSelect={() => selectOption(option.id)}
                  />
                </GridItem>
              ))}
            </Grid>
          </Stack>

          {selectedOption ? (
            <StartOptionDetail
              option={selectedOption}
              workspace={workspace}
              selectedTemplate={selectedTemplate}
              onSelectTemplate={setSelectedTemplate}
              onValidConfig={handleValidConfig}
            />
          ) : null}

          {templateError || savedTemplateError ? (
            <Banner kind="inline" status="error">
              {templateError ?? savedTemplateError}
            </Banner>
          ) : null}
        </Stack>
      </Block>

      {selectedOption ? (
        <Flex
          align="center"
          justify="end"
          className="shrink-0 gap-4 border-t border-base bg-surface-base px-10 py-4"
        >
          {!canContinue && !isSettingUp && BLOCKED_HINT[selectedOption.id] ? (
            <Text kind="body/regular/sm" className="text-secondary">
              {BLOCKED_HINT[selectedOption.id]}
            </Text>
          ) : null}
          <Button
            color="brand"
            kind="primary"
            onClick={() => void handleContinue()}
            disabled={!canContinue}
          >
            {isSettingUp ? (
              <Flex align="center" gap="density-xs">
                <Spinner size="small" className="h-4 w-4" aria-label="Setting up" />
                {statusLabel}
              </Flex>
            ) : (
              <>
                Continue
                <ArrowRight size={16} aria-hidden />
              </>
            )}
          </Button>
        </Flex>
      ) : null}
    </Stack>
  );
};
