// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { METRIC_LABELS } from '@nemo/common/src/constants/metrics';
import {
  MetricsCheckboxes,
  MetricOption,
} from '@studio/components/evaluation/Configurations/form/MetricsCheckboxes';
import { ROUTES } from '@studio/constants/routes';
import { renderWithRouter, screen } from '@studio/tests/util/render';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { FormProvider, useForm } from 'react-hook-form';
import { generatePath } from 'react-router-dom';

const queryClient = new QueryClient();

const NUM_METRICS = 6;

describe('MetricsCheckboxes', () => {
  const testPath = generatePath(ROUTES.workspace.index, {
    workspace: 'test-workspace',
  });

  const mockedDefaultValues = {
    configData: {
      evaluationType: 'custom',
      name: 'config name here',
      metrics: ['bleu'],
    },
  };

  // Wrapper component that provides the FormProvider context
  const Wrapper = ({
    formDisabled,
    children,
  }: {
    formDisabled?: boolean;
    children: React.ReactNode;
  }) => {
    const methods = useForm({
      defaultValues: mockedDefaultValues,
      disabled: formDisabled,
    });
    return (
      <QueryClientProvider client={queryClient}>
        <FormProvider {...methods}>{children}</FormProvider>
      </QueryClientProvider>
    );
  };

  it('should render MetricsCheckboxes', async () => {
    renderWithRouter({
      history: testPath,
      overrideRoutes: [
        {
          path: ROUTES.workspace.index,
          element: (
            <Wrapper>
              <MetricsCheckboxes />
            </Wrapper>
          ),
        },
      ],
    });

    // Wait for component to render
    expect(await screen.findByText(METRIC_LABELS.bleu)).toBeInTheDocument();
    expect(screen.getAllByTestId('nv-checkbox-input')).toHaveLength(NUM_METRICS);
    expect(screen.getByText(METRIC_LABELS.rouge)).toBeInTheDocument();
    expect(screen.getByText(METRIC_LABELS.em)).toBeInTheDocument();
    expect(screen.getByText(METRIC_LABELS.f1)).toBeInTheDocument();
    expect(screen.getByText(METRIC_LABELS['string-check'])).toBeInTheDocument();
    expect(screen.getByText(METRIC_LABELS['llm-judge'])).toBeInTheDocument();
  });

  it('should disable MetricsCheckboxes when form is disabled', async () => {
    renderWithRouter({
      history: testPath,
      overrideRoutes: [
        {
          path: ROUTES.workspace.index,
          element: (
            <Wrapper formDisabled>
              <MetricsCheckboxes />
            </Wrapper>
          ),
        },
      ],
    });

    // Wait for component to render
    await screen.findByText(METRIC_LABELS.bleu);

    const checkboxes = screen.getAllByTestId('nv-checkbox-input');
    checkboxes.forEach((checkbox) => {
      expect(checkbox).toBeDisabled();
    });
  });

  it('should not proceed with click handling in MetricOption if disabled', async () => {
    const user = userEvent.setup();
    const mockOnChange = vi.fn();

    renderWithRouter({
      history: testPath,
      overrideRoutes: [
        {
          path: ROUTES.workspace.index,
          element: <MetricOption disabled label="bleu" value={['bleu']} onChange={mockOnChange} />,
        },
      ],
    });

    await user.click(await screen.findByText(METRIC_LABELS.bleu));
    expect(mockOnChange).not.toHaveBeenCalled();
  });
});
