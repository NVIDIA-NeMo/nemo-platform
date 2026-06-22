// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { InputFile } from '@studio/components/evaluation/Configurations/form/InputFile';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render as rawRender, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FC, PropsWithChildren } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

describe('InputFile', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE,
    });
  });
  const mockedDefaultValues = {
    configData: {
      evaluationType: 'custom',
    },
  };

  const Wrapper: FC<PropsWithChildren> = ({ children }) => {
    const methods = useForm({
      defaultValues: mockedDefaultValues,
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

  it('should render InputFile', async () => {
    const user = userEvent.setup();

    rawRender(
      <Wrapper>
        <InputFile />
      </Wrapper>
    );

    expect(await screen.findByRole('button', { name: 'Select File' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Select File' }));

    // Modal opens with dataset selector
    await screen.findByText('Select a File');
    await screen.findByText('Dataset');
  });
});
