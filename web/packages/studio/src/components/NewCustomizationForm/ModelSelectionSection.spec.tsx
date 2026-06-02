// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { type ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { NEW_CUSTOMIZATION_FORM_HYP_DEFAULT_VALUES } from '@studio/components/NewCustomizationForm/constants';
import { ModelSelectionSection } from '@studio/components/NewCustomizationForm/ModelSelectionSection';
import { parentModels } from '@studio/mocks/customizer/parent-models';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useFormContext } from 'react-hook-form';

const findModelItemByName = (name: string) =>
  screen
    .getAllByTestId('model-dropdown-item')
    .find((item) => within(item).queryByText(name) !== null);

const queryModelItemByName = (name: string) =>
  screen
    .queryAllByTestId('model-dropdown-item')
    .find((item) => within(item).queryByText(name) !== null);

const modelsWithFileset: ModelEntity[] = parentModels.map((m) => ({
  ...m,
  fileset: `default/${m.name}-fileset`,
}));

const modelWithAdapters: ModelEntity = {
  id: 'model-with-adapters',
  name: 'adaptable-base-model',
  workspace: 'default',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  fileset: 'default/adaptable-base-model-fileset',
  adapters: [
    {
      name: 'sample-adapter',
      workspace: 'default',
      fileset: 'default/sample-adapter-fileset',
      finetuning_type: 'lora',
      created_at: '2024-02-01T00:00:00Z',
    },
  ],
};

const TrainingValueSpy = () => {
  const { watch } = useFormContext();
  const training = watch('training');
  return <span data-testid="training-spy">{JSON.stringify(training)}</span>;
};

const openModelDropdown = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByTestId('model-select-v2-trigger'));
};

describe('ModelSelectionSection', () => {
  it('should render section title and form fields', () => {
    render(
      <FormWrapper>
        <ModelSelectionSection />
      </FormWrapper>
    );

    expect(screen.getByText('Model Selection')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Output Model Name' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Description (optional)' })).toBeInTheDocument();
  });

  it('should render model options in the dropdown', async () => {
    const user = userEvent.setup();
    render(
      <FormWrapper>
        <ModelSelectionSection models={modelsWithFileset} isFetchingModels={false} />
      </FormWrapper>
    );

    await openModelDropdown(user);

    for (const model of modelsWithFileset) {
      expect(findModelItemByName(model.name!)).toBeDefined();
    }
  });

  it('should disable model select when fetching models', () => {
    render(
      <FormWrapper>
        <ModelSelectionSection models={modelsWithFileset} isFetchingModels />
      </FormWrapper>
    );

    expect(screen.getByTestId('model-select-v2-trigger')).toBeDisabled();
  });

  it('should only show models that have a fileset', async () => {
    const modelWithFileset: ModelEntity = {
      id: 'model-with-fileset',
      name: 'fileset-model',
      workspace: 'default',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      fileset: 'default/fileset-model-fileset',
    };
    const user = userEvent.setup();
    render(
      <FormWrapper>
        <ModelSelectionSection
          models={[...parentModels, modelWithFileset]}
          isFetchingModels={false}
        />
      </FormWrapper>
    );

    await openModelDropdown(user);

    for (const model of parentModels) {
      expect(queryModelItemByName(model.name!)).toBeUndefined();
    }
    expect(findModelItemByName(modelWithFileset.name!)).toBeDefined();
  });

  it('should hide adapters from the dropdown', async () => {
    const user = userEvent.setup();
    render(
      <FormWrapper>
        <ModelSelectionSection models={[modelWithAdapters]} isFetchingModels={false} />
      </FormWrapper>
    );

    await openModelDropdown(user);

    expect(findModelItemByName(modelWithAdapters.name!)).toBeDefined();
    expect(screen.queryByText('sample-adapter')).toBeNull();
    expect(screen.queryByTestId('model-dropdown-item-with-adapters')).toBeNull();
    expect(screen.getByTestId('model-dropdown-item')).toBeInTheDocument();
  });

  it('should reset training defaults when model selection changes', async () => {
    const user = userEvent.setup();
    render(
      <FormWrapper
        formProps={{
          defaultValues: { training: { type: 'sft', epochs: 99 } },
        }}
      >
        <ModelSelectionSection models={modelsWithFileset} isFetchingModels={false} />
        <TrainingValueSpy />
      </FormWrapper>
    );

    await openModelDropdown(user);
    const firstItem = findModelItemByName(modelsWithFileset[0].name!);
    expect(firstItem).toBeDefined();
    await user.click(firstItem!);

    expect(screen.getByTestId('training-spy')).toHaveTextContent(
      JSON.stringify(NEW_CUSTOMIZATION_FORM_HYP_DEFAULT_VALUES)
    );
  });
});
