// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { ParameterEfficiency } from '@studio/components/NewCustomizationForm/ParameterEfficiency';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const renderParameterEfficiency = async (defaultValues?: Record<string, unknown>) => {
  // eslint-disable-next-line testing-library/no-unnecessary-act -- KUI Select triggers deferred Ariakit state updates
  await act(async () => {
    render(
      <FormWrapper formProps={{ defaultValues }}>
        <ParameterEfficiency />
      </FormWrapper>
    );
  });
};

describe('ParameterEfficiency', () => {
  it('should render section title and radio options', () => {
    render(
      <FormWrapper>
        <ParameterEfficiency />
      </FormWrapper>
    );

    expect(screen.getByText('Parameter Efficiency')).toBeInTheDocument();
    expect(screen.getByText('LoRA')).toBeInTheDocument();
    expect(screen.getByText('Full Weights Fine-tuning')).toBeInTheDocument();
  });

  it('should render LoRA parameters when LoRA is selected by default', async () => {
    await renderParameterEfficiency({
      training: { peft: { rank: 8, alpha: 16, dropout: 0.1, merge: false } },
    });

    expect(screen.getByText('Rank')).toBeInTheDocument();
    expect(screen.getByText('Enable QLoRA')).toBeInTheDocument();
  });

  it('should not render LoRA parameters when full weights is selected', () => {
    render(
      <FormWrapper formProps={{ defaultValues: { training: {} } }}>
        <ParameterEfficiency />
      </FormWrapper>
    );

    expect(screen.queryByText('Rank')).not.toBeInTheDocument();
    expect(screen.queryByText('Enable QLoRA')).not.toBeInTheDocument();
  });

  it('should show merge weights toggle inside LoRA card', async () => {
    await renderParameterEfficiency({
      training: { peft: { rank: 8, merge: false } },
    });

    expect(screen.getByText('Merge Weights')).toBeInTheDocument();
  });

  it('should switch to full weights when clicked', async () => {
    const user = userEvent.setup();
    await renderParameterEfficiency({
      training: { peft: { rank: 8 } },
    });

    const fullWeightsRadio = screen.getByRole('radio', { name: /Full Weights/ });
    await user.click(fullWeightsRadio);

    expect(fullWeightsRadio).toBeChecked();
    expect(screen.queryByText('Rank')).not.toBeInTheDocument();
  });
});
