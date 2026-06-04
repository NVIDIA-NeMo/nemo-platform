// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MetricDetailsSection } from '@studio/components/evaluation/Jobs/form/MetricDetailsSection';
import { renderRoute } from '@studio/tests/util/render';
import { screen } from '@testing-library/react';
import { FormProvider, useForm } from 'react-hook-form';

function renderSection() {
  const Wrapper = () => {
    const methods = useForm({
      defaultValues: { name: '', body: { description: '' } },
    });
    return (
      <FormProvider {...methods}>
        <MetricDetailsSection />
      </FormProvider>
    );
  };

  return renderRoute(<Wrapper />);
}

describe('MetricDetailsSection', () => {
  it('renders metric name and description fields', async () => {
    renderSection();

    expect(await screen.findByText('Metric Name')).toBeInTheDocument();
    expect(screen.getByText('Description (optional)')).toBeInTheDocument();
  });

  it('renders an input for the metric name', async () => {
    renderSection();

    await screen.findByText('Metric Name');
    // KUI TextInput renders as a textbox role
    expect(screen.getAllByRole('textbox').length).toBeGreaterThan(0);
  });
});
