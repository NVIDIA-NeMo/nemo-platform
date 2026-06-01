// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { LoraParameters } from '@studio/components/customizer/CustomizationHyperparameters/LoraParameters';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const renderLoraParameters = async () => {
  // eslint-disable-next-line testing-library/no-unnecessary-act -- KUI Select triggers deferred Ariakit state updates
  await act(async () => {
    render(
      <FormWrapper formProps={{ defaultValues: { training: { peft: { rank: 8 } } } }}>
        <LoraParameters />
      </FormWrapper>
    );
  });
};

describe('LoraParameters', () => {
  it('should render primary parameters', async () => {
    await renderLoraParameters();

    expect(screen.getByText('Rank')).toBeInTheDocument();
    expect(screen.getByText('Enable QLoRA')).toBeInTheDocument();
  });

  it('should render advanced parameters when accordion is expanded', async () => {
    const user = userEvent.setup();
    await renderLoraParameters();

    const accordion = screen.getByText('Show Advanced LoRA Parameters');
    await user.click(accordion);

    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Dropout')).toBeInTheDocument();
    expect(screen.getByText('Target Modules')).toBeInTheDocument();
  });

  it('should not render advanced parameters before accordion is expanded', async () => {
    await renderLoraParameters();

    expect(screen.queryByText('Alpha')).not.toBeVisible();
    expect(screen.queryByText('Dropout')).not.toBeVisible();
    expect(screen.queryByText('Target Modules')).not.toBeVisible();
  });

  it('should show QLoRA precision selector when QLoRA is enabled', async () => {
    const user = userEvent.setup();
    await renderLoraParameters();

    const qloraSwitch = screen.getByRole('switch');
    await user.click(qloraSwitch);

    await waitFor(() => {
      expect(screen.getByText('QLoRA Precision')).toBeInTheDocument();
    });
  });
});
