// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccordionSection } from '@nemo/common/src/components/AccordionSection';
import {
  DEFAULT_PROMPT_TEMPLATE,
  DEFAULT_PROMPT_TEMPLATE_COMPILED,
} from '@nemo/common/src/models/constants';
import { compileSystemPrompt } from '@nemo/common/src/models/utils';
import { Button, Flex, FormField, Stack, TextArea } from '@nvidia/foundations-react-core';
import type {
  PromptTuningFormFields,
  PromptTuningFormSectionProps,
} from '@studio/routes/PromptTuningFormRoute/utils';
import { RotateCcw, PenLine } from 'lucide-react';
import { ChangeEvent, FC } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

/**
 * React hook form connected component for showing/editing the prompt template field
 */
export const PromptTemplateSection: FC<PromptTuningFormSectionProps> = () => {
  const {
    formState: { errors, disabled },
    register,
    setValue,
    control,
  } = useFormContext<PromptTuningFormFields>();

  const iclFewShotExamples = useWatch({ control, name: 'iclFewShotExamples' });
  const systemPromptTemplate = useWatch({ control, name: 'systemPromptTemplate' });

  const setCompiledSystemPrompt = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const newSystemPromptTemplate = event.target.value;
    try {
      const compiledSystemPrompt = compileSystemPrompt({
        systemPromptTemplate: newSystemPromptTemplate,
        iclFewShotExamples: iclFewShotExamples?.map((icl) => icl.content).join('\n'),
      }).prompt;
      setValue('systemPrompt', compiledSystemPrompt, { shouldValidate: true });
    } catch {
      // No need to do anything here, RHF's resolver will catch this
    }
  };

  const handleResetToDefault = () => {
    setValue('systemPromptTemplate', DEFAULT_PROMPT_TEMPLATE, {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue('systemPrompt', DEFAULT_PROMPT_TEMPLATE_COMPILED, { shouldValidate: true });
  };

  return (
    <AccordionSection title="System Prompt" value="system-prompt" icon={<PenLine />}>
      <Stack gap="density-md">
        <p>
          A system prompt allows you to tailor and refine the behavior of an AI by providing
          specific instructions or constraints that will influence its output.
        </p>
        <input type="hidden" {...register('systemPrompt')} />

        <FormField
          name="systemPromptTemplate"
          slotLabel="Template Format"
          slotError={errors.systemPromptTemplate?.message || ''}
          status={errors.systemPromptTemplate ? 'error' : undefined}
          slotHelp="Prompt templates can be configured in Handlebars syntax"
        >
          <TextArea
            required
            className="resize-y"
            {...register('systemPromptTemplate', { onChange: setCompiledSystemPrompt })}
            value={systemPromptTemplate ?? ''}
            placeholder="Provide a direct command or explanation of what you would like the model to do."
            status={errors.systemPromptTemplate && 'error'}
          />
        </FormField>
        <Flex justify="end">
          <Button
            onClick={handleResetToDefault}
            type="reset"
            kind="tertiary"
            disabled={disabled || systemPromptTemplate === DEFAULT_PROMPT_TEMPLATE}
          >
            <RotateCcw />
            Reset Prompt
          </Button>
        </Flex>
      </Stack>
    </AccordionSection>
  );
};
