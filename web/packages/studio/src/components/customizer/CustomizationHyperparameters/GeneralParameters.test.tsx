// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { GeneralParameters } from '@studio/components/customizer/CustomizationHyperparameters/GeneralParameters';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('GeneralParameters', () => {
  it('should render primary training parameters', () => {
    render(
      <FormWrapper>
        <GeneralParameters />
      </FormWrapper>
    );

    expect(screen.getByText('Training Parameters')).toBeInTheDocument();
    expect(screen.getByText('Epochs')).toBeInTheDocument();
    expect(screen.getByText('Learning Rate')).toBeInTheDocument();
    expect(screen.getByText('Batch Size')).toBeInTheDocument();
    expect(screen.getByText('Max Seq Length')).toBeInTheDocument();
    expect(screen.getByText('Sequence Packing')).toBeInTheDocument();
  });

  it('should render advanced parameters when accordion is expanded', async () => {
    const user = userEvent.setup();
    render(
      <FormWrapper>
        <GeneralParameters />
      </FormWrapper>
    );

    const accordion = screen.getByText('Show Advanced Training Parameters');
    await user.click(accordion);

    expect(screen.getByText('Micro Batch Size')).toBeInTheDocument();
    expect(screen.getByText('Warmup Steps')).toBeInTheDocument();
    expect(screen.getByText('Weight Decay')).toBeInTheDocument();
    expect(screen.getByText('Min Learning Rate')).toBeInTheDocument();
    expect(screen.getByText('Precision')).toBeInTheDocument();
    expect(screen.getByText('Optimizer')).toBeInTheDocument();
    expect(screen.getByText('Seed')).toBeInTheDocument();
    expect(screen.getByText('Log Every N Steps')).toBeInTheDocument();
    expect(screen.getByText('Val Check Interval')).toBeInTheDocument();
    expect(screen.getByText('Max Steps')).toBeInTheDocument();
  });

  it('should not render advanced parameters before accordion is expanded', () => {
    render(
      <FormWrapper>
        <GeneralParameters />
      </FormWrapper>
    );

    expect(screen.queryByText('Micro Batch Size')).not.toBeVisible();
    expect(screen.queryByText('Max Steps')).not.toBeVisible();
  });
});
