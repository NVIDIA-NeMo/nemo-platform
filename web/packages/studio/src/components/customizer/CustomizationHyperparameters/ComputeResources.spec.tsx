// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { ComputeResources } from '@studio/components/customizer/CustomizationHyperparameters/ComputeResources';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('ComputeResources', () => {
  it('should render primary compute resource fields', () => {
    render(
      <FormWrapper>
        <ComputeResources />
      </FormWrapper>
    );

    expect(screen.getByText('Compute Resources')).toBeInTheDocument();
    expect(screen.getByText('Num Nodes')).toBeInTheDocument();
    expect(screen.getByText('Num Gpus Per Node')).toBeInTheDocument();
  });

  it('should render advanced parallelism fields when accordion is expanded', async () => {
    const user = userEvent.setup();
    render(
      <FormWrapper>
        <ComputeResources />
      </FormWrapper>
    );

    const accordion = screen.getByText('Show Advanced Parallelism');
    await user.click(accordion);

    expect(screen.getByText('Tensor Parallel Size')).toBeInTheDocument();
    expect(screen.getByText('Pipeline Parallel Size')).toBeInTheDocument();
    expect(screen.getByText('Context Parallel Size')).toBeInTheDocument();
    expect(screen.getByText('Expert Parallel Size')).toBeInTheDocument();
    expect(screen.getByText('Sequence Parallel')).toBeInTheDocument();
  });

  it('should not render advanced parallelism fields before accordion is expanded', () => {
    render(
      <FormWrapper>
        <ComputeResources />
      </FormWrapper>
    );

    expect(screen.queryByText('Tensor Parallel Size')).not.toBeVisible();
    expect(screen.queryByText('Pipeline Parallel Size')).not.toBeVisible();
  });
});
