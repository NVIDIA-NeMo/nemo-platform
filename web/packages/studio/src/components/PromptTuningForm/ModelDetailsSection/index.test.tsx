// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { compileSystemPrompt } from '@nemo/common/src/models/utils';
import { ModelDetailsSection } from '@studio/components/PromptTuningForm/ModelDetailsSection/index';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import {
  PromptTuningFormFields,
  DEFAULT_PROMPT_TUNING_FORM_VALUES,
  promptTuningFormSchema,
} from '@studio/routes/PromptTuningFormRoute/utils';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { render } from '@studio/tests/util/render';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormProvider, useForm } from 'react-hook-form';

// Mock the ModelSelectV2 component
vi.mock('@nemo/common/src/components/ModelSelectV2', () => ({
  ModelSelectV2: () => <div data-testid="model-select">Model Select</div>,
}));

const FormWrapper = ({
  children,
  onFormChange,
}: {
  children: React.ReactNode;
  onFormChange?: (form: ReturnType<typeof useForm<PromptTuningFormFields>>) => void;
}) => {
  const methods = useForm<PromptTuningFormFields>({
    defaultValues: DEFAULT_PROMPT_TUNING_FORM_VALUES,
    mode: 'onChange',
    resolver: zodResolver(promptTuningFormSchema),
  });

  if (onFormChange) {
    onFormChange(methods);
  }

  return <FormProvider {...methods}>{children}</FormProvider>;
};

describe('ModelDetailsSection', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE,
    });
  });

  it('should compile system prompt when template changes', async () => {
    const user = userEvent.setup();
    let formMethods: ReturnType<typeof useForm<PromptTuningFormFields>> | undefined;

    render(
      <FormWrapper
        onFormChange={(form) => {
          formMethods = form;
        }}
      >
        <ModelDetailsSection />
      </FormWrapper>
    );

    const systemPromptInput = screen.getByRole('textbox', { name: 'System Instructions' });

    await user.clear(systemPromptInput);
    await user.type(systemPromptInput, 'You are a helpful assistant.');

    expect(formMethods?.getValues('systemPromptTemplate')).toBe('You are a helpful assistant.');
    expect(formMethods?.getValues('systemPrompt')).toBe('You are a helpful assistant.');
  });

  it('should include ICL few shot examples in compilation', async () => {
    const user = userEvent.setup();
    let formMethods: ReturnType<typeof useForm<PromptTuningFormFields>> | undefined;

    const FormWrapperWithICL = ({ children }: { children: React.ReactNode }) => {
      const methods = useForm<PromptTuningFormFields>({
        defaultValues: {
          ...DEFAULT_PROMPT_TUNING_FORM_VALUES,
          iclFewShotExamples: [
            { content: 'Example 1', fileName: 'file1.txt' },
            { content: 'Example 2', fileName: 'file2.txt' },
          ],
        },
      });

      formMethods = methods;
      return <FormProvider {...methods}>{children}</FormProvider>;
    };

    render(
      <FormWrapperWithICL>
        <ModelDetailsSection />
      </FormWrapperWithICL>
    );

    const systemPromptInput = screen.getByRole('textbox', { name: 'System Instructions' });

    await user.clear(systemPromptInput);
    await user.type(systemPromptInput, 'You are a helpful assistant.');

    expect(formMethods?.getValues('systemPromptTemplate')).toBe('You are a helpful assistant.');
    expect(formMethods?.getValues('systemPrompt')).toBe(
      compileSystemPrompt({
        systemPromptTemplate: 'You are a helpful assistant.',
        iclFewShotExamples: 'Example 1\nExample 2',
      }).prompt
    );
  });

  it('should handle compilation errors gracefully', async () => {
    const user = userEvent.setup();

    render(
      <FormWrapper>
        <ModelDetailsSection />
      </FormWrapper>
    );

    const systemPromptInput = screen.getByRole('textbox', { name: 'System Instructions' });

    await user.clear(systemPromptInput);
    await user.type(systemPromptInput, 'Invalid template {{');
    await user.keyboard('{{');
    await user.keyboard('icl_few_shot_examples');
    expect(screen.getByText('Invalid system prompt template')).toBeInTheDocument();
  });
});
