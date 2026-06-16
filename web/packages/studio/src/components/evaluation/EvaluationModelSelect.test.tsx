// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { EvaluationModelSelect } from '@studio/components/evaluation/EvaluationModelSelect';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render as rawRender, screen } from '@testing-library/react';
import { FC, PropsWithChildren } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

describe('EvaluationModelSelect', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE,
    });
  });
  const mockedDefaultValues = {
    evaluationType: 'custom',
  };

  // Wrapper component that provides the FormProvider context
  const FormWrapper: FC<PropsWithChildren> = ({ children }) => {
    const methods = useForm({
      defaultValues: {
        online: mockedDefaultValues,
        offline: mockedDefaultValues,
      },
    });

    return (
      <TestProviders>
        <MemoryRouter initialEntries={['/projects/test-namespace/test-project']}>
          <Routes>
            <Route
              path="/projects/:projectNamespace/:projectName"
              element={<FormProvider {...methods}>{children}</FormProvider>}
            />
          </Routes>
        </MemoryRouter>
      </TestProviders>
    );
  };

  it('should render EvaluationModelSelect', async () => {
    rawRender(
      <FormWrapper>
        <EvaluationModelSelect formFieldName="targetModel" />
      </FormWrapper>
    );

    expect(await screen.findByText('Model')).toBeInTheDocument();
  });
});
