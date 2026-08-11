// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelSettingsSection } from '@studio/routes/AnonymizerBuilderRoute/components/ModelSettingsSection';
import {
  activeRolesForStrategy,
  STRATEGY_SUBSTITUTE,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import {
  AnonymizerFormData,
  getAnonymizerFormDefaults,
} from '@studio/routes/AnonymizerBuilderRoute/schema';
import { render, screen } from '@testing-library/react';
import { FC, ReactNode } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

vi.mock('@studio/routes/AnonymizerBuilderRoute/useAnonymizerModels', () => ({
  useAnonymizerModels: () => ({
    models: [],
    items: [{ label: 'gpt-oss-120b', value: 'gpt-oss-120b' }],
    isLoading: false,
    applyModel: vi.fn(),
  }),
}));

const TestWrapper: FC<{ children: ReactNode }> = ({ children }) => {
  const methods = useForm<AnonymizerFormData>({ defaultValues: getAnonymizerFormDefaults() });
  return <FormProvider {...methods}>{children}</FormProvider>;
};

describe('ModelSettingsSection', () => {
  it('offers sampling params for every role except the GLiNER detector', async () => {
    render(
      <TestWrapper>
        <ModelSettingsSection />
      </TestWrapper>
    );

    const triggers = await screen.findAllByTestId('params-dropdown-trigger');
    expect(triggers).toHaveLength(activeRolesForStrategy(STRATEGY_SUBSTITUTE).length - 1);
  });
});
