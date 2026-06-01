// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { DpoParameters } from '@studio/components/customizer/CustomizationHyperparameters/DpoParameters';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('DpoParameters', () => {
  it('should render the section title and primary parameter', () => {
    render(
      <FormWrapper>
        <DpoParameters />
      </FormWrapper>
    );

    expect(screen.getByText('DPO Parameters')).toBeInTheDocument();
    expect(screen.getByText('Max Grad Norm')).toBeInTheDocument();
  });

  it('should render advanced DPO parameters when accordion is expanded', async () => {
    const user = userEvent.setup();
    render(
      <FormWrapper>
        <DpoParameters />
      </FormWrapper>
    );

    const accordion = screen.getByText('Show Advanced DPO Parameters');
    await user.click(accordion);

    expect(screen.getByText('Ref Policy KL Penalty')).toBeInTheDocument();
    expect(screen.getByText('Preference Loss Weight')).toBeInTheDocument();
    expect(screen.getByText('Preference Average Log Probs')).toBeInTheDocument();
    expect(screen.getByText('SFT Loss Weight')).toBeInTheDocument();
    expect(screen.getByText('SFT Average Log Probs')).toBeInTheDocument();
  });

  it('should not render advanced DPO parameters before accordion is expanded', () => {
    render(
      <FormWrapper>
        <DpoParameters />
      </FormWrapper>
    );

    expect(screen.queryByText('Ref Policy KL Penalty')).not.toBeVisible();
    expect(screen.queryByText('Preference Loss Weight')).not.toBeVisible();
  });
});
