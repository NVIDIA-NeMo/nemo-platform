// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { CustomizationOverview } from '@studio/components/CustomizationOverview';
import { customizationJob1 } from '@studio/mocks/customizer/customization-jobs';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { getBaseModel } from '@studio/util/customizations';
import { render, screen, waitForElementToBeRemoved } from '@testing-library/react';

const renderOverview = async () => {
  render(
    <TestProviders>
      <CustomizationOverview
        customizationJobName={customizationJob1.name!}
        workspace={customizationJob1.workspace}
      />
    </TestProviders>
  );
  await waitForElementToBeRemoved(() => screen.queryByText('Loading...'), {
    timeout: XL_SELECTOR_TIMEOUT,
  });
};

describe('CustomizationOverview', () => {
  it('summarizes the training results as stat tiles', async () => {
    await renderOverview();

    expect(await screen.findByText('Final Training Loss')).toBeInTheDocument();
    expect(screen.getByText('Final Validation Loss')).toBeInTheDocument();
    expect(screen.getAllByText('0.9000')).toHaveLength(2);

    expect(screen.getByText('Steps Completed')).toBeInTheDocument();
    expect(screen.getByText('10 / 10')).toBeInTheDocument();
    expect(screen.getByText('Epochs Completed')).toBeInTheDocument();
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
  });

  it('surfaces the live per-step telemetry as diagnostics tiles', async () => {
    await renderOverview();

    expect(await screen.findByText('Learning Rate')).toBeInTheDocument();
    expect(screen.getByText((5e-6).toExponential(2))).toBeInTheDocument();
    expect(screen.getByText('Gradient Norm')).toBeInTheDocument();
    expect(screen.getByText('1.2345')).toBeInTheDocument();

    expect(screen.getByText('Train/Val Gap')).toBeInTheDocument();
    expect(screen.getByText('0.0000')).toBeInTheDocument();

    expect(screen.getByText('Duration')).toBeInTheDocument();
    expect(screen.getByText('00:01:12')).toBeInTheDocument();
    expect(screen.queryByText('Phase')).not.toBeInTheDocument();
  });

  it('renders the run configuration', async () => {
    await renderOverview();

    expect(await screen.findByText('Run configuration')).toBeInTheDocument();

    expect(screen.getByText('Customization ID')).toBeInTheDocument();
    expect(screen.getByText(customizationJob1.id!)).toBeInTheDocument();

    expect(screen.getByText('Output Model')).toBeInTheDocument();
    expect(screen.getByText(customizationJob1.spec?.output?.name ?? '-')).toBeInTheDocument();

    expect(screen.getByText('Base Model')).toBeInTheDocument();
    expect(screen.getByText(getBaseModel(customizationJob1) || '-')).toBeInTheDocument();

    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText(customizationJob1.description!)).toBeInTheDocument();

    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(
      screen.getByText(
        customizationJob1.created_at ? formatAbsoluteTimestamp(customizationJob1.created_at) : '-'
      )
    ).toBeInTheDocument();

    expect(screen.getByText('Latest Checkpoint')).toBeInTheDocument();
    expect(screen.getByText('default/output-fileset/checkpoints/step-10')).toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'View Job Configuration' })).toBeInTheDocument();
  });

  it('renders the training loss chart panel', async () => {
    await renderOverview();

    expect(await screen.findByText('Training loss')).toBeInTheDocument();
  });

  it('no longer renders status logs — they moved to their own tab', async () => {
    await renderOverview();

    expect(await screen.findByText('Run configuration')).toBeInTheDocument();
    expect(screen.queryByText('Status Logs')).not.toBeInTheDocument();
  });
});
