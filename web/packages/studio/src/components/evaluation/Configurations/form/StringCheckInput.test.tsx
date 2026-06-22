// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StringCheckInput } from '@studio/components/evaluation/Configurations/form/StringCheckInput';
import { useCreateConfigForm } from '@studio/hooks/evaluation/useCreateConfigurationForm';
import { render, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { FormProvider } from 'react-hook-form';

describe('StringCheckInput', () => {
  // Wrapper component that provides the FormProvider context
  // Note: QueryClientProvider is already provided by render via TestProviders
  const Wrapper = ({ disabled, children }: { disabled?: boolean; children: React.ReactNode }) => {
    const methods = useCreateConfigForm({ disabled });
    return <FormProvider {...methods}>{children}</FormProvider>;
  };

  it('should render with default state and allow changing operators', async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <StringCheckInput />
      </Wrapper>
    );

    // Check labels are rendered (component shows: Actual Response, Operator, Ground Truth)
    expect(await screen.findByText('Actual Response')).toBeInTheDocument();
    expect(screen.getByText('Operator')).toBeInTheDocument();
    expect(screen.getByText('Ground Truth')).toBeInTheDocument();

    // Check operator dropdown has default value "equals"
    const selectTrigger = screen.getByRole('combobox', { name: /Operator/i });
    expect(selectTrigger).toHaveTextContent('equals');

    // Open dropdown and verify all operator options are available
    await user.click(selectTrigger);
    const operators = ['equals', '!=', 'contains', 'startswith', 'endswith'];
    for (const operator of operators) {
      expect(await screen.findByRole('option', { name: operator })).toBeInTheDocument();
    }

    // Select a different operator and verify it updates
    const containsOption = screen.getByRole('option', { name: 'contains' });
    await user.click(containsOption);

    await waitFor(() => {
      expect(selectTrigger).toHaveTextContent('contains');
    });
  });

  it('should disable the operator dropdown when disabled prop is true', async () => {
    render(
      <Wrapper disabled>
        <StringCheckInput disabled />
      </Wrapper>
    );

    const selectTrigger = await screen.findByRole('combobox', { name: /Operator/i });
    expect(selectTrigger).toBeDisabled();
  });
});
