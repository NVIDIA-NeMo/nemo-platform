// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccordionSection } from '@nemo/common/src/components/AccordionSection';
import { InferenceParameters } from '@nemo/common/src/components/ModelSelectV2/InferenceParameters';
import type { InferenceParams } from '@nemo/sdk/generated/platform/schema';
import type {
  PromptTuningFormFields,
  PromptTuningFormSectionProps,
} from '@studio/routes/PromptTuningFormRoute/utils';
import { SlidersHorizontal } from 'lucide-react';
import { FC, useCallback, useMemo } from 'react';
import { type Path, useFormContext, useWatch } from 'react-hook-form';

const INFERENCE_FORM_KEYS = [
  'max_tokens',
  'temperature',
  'top_p',
  'max_completion_tokens',
] as const satisfies readonly Path<PromptTuningFormFields>[];

type InferenceFormKey = (typeof INFERENCE_FORM_KEYS)[number];

const isInferenceFormKey = (key: string): key is InferenceFormKey =>
  (INFERENCE_FORM_KEYS as readonly string[]).includes(key);

export const InferenceParametersSection: FC<PromptTuningFormSectionProps> = ({ isEditable }) => {
  const {
    control,
    setValue,
    formState: { disabled: formDisabled },
  } = useFormContext<PromptTuningFormFields>();

  const max_tokens = useWatch({ control, name: 'max_tokens' });
  const temperature = useWatch({ control, name: 'temperature' });
  const top_p = useWatch({ control, name: 'top_p' });
  const max_completion_tokens = useWatch({ control, name: 'max_completion_tokens' });

  const inferenceParams = useMemo(
    (): Partial<InferenceParams> => ({
      max_tokens,
      temperature,
      top_p,
      max_completion_tokens,
    }),
    [max_tokens, temperature, top_p, max_completion_tokens]
  );

  const handleInferenceChange = useCallback(
    (next: Partial<InferenceParams>) => {
      for (const [rawKey, val] of Object.entries(next)) {
        if (val === undefined || val === null || typeof val !== 'number') continue;
        if (!isInferenceFormKey(rawKey)) continue;
        setValue(rawKey, val, { shouldDirty: true, shouldValidate: true });
      }
    },
    [setValue]
  );

  const disabled = formDisabled || isEditable === false;

  return (
    <AccordionSection
      value="model-hyperparameters"
      title="Hyperparameters"
      icon={<SlidersHorizontal />}
    >
      <InferenceParameters
        value={inferenceParams}
        onChange={handleInferenceChange}
        disabled={disabled}
      />
    </AccordionSection>
  );
};
