// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RadioCard } from '@nemo/common/src/components/RadioCard';
import { Anchor, Block, FormField, Grid, RadioGroupRoot } from '@nvidia/foundations-react-core';
import type { CustomizationFormFields } from '@studio/components/NewCustomizationForm';
import {
  isTrainingType,
  TRAINING_DEFAULTS_BY_TYPE,
  TRAINING_METHOD_OPTIONS,
} from '@studio/components/NewCustomizationForm/constants';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import { LINK_DOCS_FINE_TUNE_CONFIGURATION_DECISIONS } from '@studio/constants/links';
import { useController, useFormContext, useWatch } from 'react-hook-form';

export const TrainingMethodSelect = () => {
  const {
    control,
    formState: { disabled },
    setValue,
    clearErrors,
  } = useFormContext<CustomizationFormFields>();

  const trainingType = useWatch({ control, name: 'training.type' });

  const {
    fieldState: { error: trainingTypeError },
  } = useController({ control, name: 'training.type' });

  const handleTrainingMethodChange = (value: string) => {
    if (!isTrainingType(value)) return;
    clearErrors('training');
    setValue('training', TRAINING_DEFAULTS_BY_TYPE[value]);
  };

  return (
    <FormSection
      title="Training Method"
      description={
        <>
          For guidance on selecting the right training approach, use the{' '}
          <Anchor href={LINK_DOCS_FINE_TUNE_CONFIGURATION_DECISIONS} target="_blank">
            decision framework
          </Anchor>
          .
        </>
      }
    >
      <Block data-testid="training-method-select">
        <FormField
          slotError={trainingTypeError?.message}
          status={trainingTypeError ? 'error' : undefined}
        >
          <RadioGroupRoot
            name="training-method"
            className="w-full"
            value={trainingType ?? ''}
            onValueChange={handleTrainingMethodChange}
            disabled={disabled}
          >
            <Grid cols={2} gap="density-xl">
              {TRAINING_METHOD_OPTIONS.map((option) => (
                <RadioCard
                  key={option.type}
                  value={option.type}
                  label={option.label}
                  description={option.description}
                  labelSide="left"
                />
              ))}
            </Grid>
          </RadioGroupRoot>
        </FormField>
      </Block>
    </FormSection>
  );
};
