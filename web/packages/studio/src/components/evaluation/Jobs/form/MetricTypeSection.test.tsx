// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MetricTypeSection } from '@studio/components/evaluation/Jobs/form/MetricTypeSection';
import { LINK_EVAL_DOCS_METRICS } from '@studio/constants/links';
import { renderRoute } from '@studio/tests/util/render';
import { screen } from '@testing-library/react';

describe('MetricTypeSection', () => {
  it('renders section heading and LLM-as-a-Judge option', async () => {
    renderRoute(<MetricTypeSection />);

    expect(await screen.findByText('Metric Type')).toBeInTheDocument();
    expect(screen.getByText('LLM-as-a-Judge')).toBeInTheDocument();
  });

  it('renders the Evaluation Metrics documentation link', async () => {
    renderRoute(<MetricTypeSection />);

    const link = await screen.findByRole('link', { name: 'Evaluation Metrics' });
    expect(link).toHaveAttribute('href', LINK_EVAL_DOCS_METRICS);
  });

  it('shows the llm-judge option as selected by default', async () => {
    renderRoute(<MetricTypeSection />);

    const radio = await screen.findByRole('radio');
    expect(radio).toBeChecked();
  });
});
