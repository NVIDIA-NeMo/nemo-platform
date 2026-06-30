// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { TrainingMethodSelect } from '@studio/components/NewCustomizationForm/TrainingMethodSelect';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('TrainingMethodSelect', () => {
  it('should render section title and all training method options', () => {
    render(
      <FormWrapper>
        <TrainingMethodSelect />
      </FormWrapper>
    );

    expect(screen.getByText('Training Method')).toBeInTheDocument();
    expect(screen.getByText('SFT')).toBeInTheDocument();
    expect(screen.getByText('DPO')).toBeInTheDocument();
  });

  it('should render descriptions for each option', () => {
    render(
      <FormWrapper>
        <TrainingMethodSelect />
      </FormWrapper>
    );

    expect(screen.getByText(/Supervised Fine-tuning/)).toBeInTheDocument();
    expect(screen.getByText(/Direct Preference Optimization/)).toBeInTheDocument();
  });

  it('should render the decision framework link', () => {
    render(
      <FormWrapper>
        <TrainingMethodSelect />
      </FormWrapper>
    );

    expect(screen.getByText('decision framework')).toBeInTheDocument();
  });

  it('should select a training method when clicked', async () => {
    const user = userEvent.setup();
    render(
      <FormWrapper formProps={{ defaultValues: { training: { type: 'sft' } } }}>
        <TrainingMethodSelect />
      </FormWrapper>
    );

    const dpoRadio = screen.getByRole('radio', { name: /DPO/ });
    await user.click(dpoRadio);

    expect(dpoRadio).toBeChecked();
  });
});
