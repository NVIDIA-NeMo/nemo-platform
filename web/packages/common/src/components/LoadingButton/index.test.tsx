// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { render, screen } from '@testing-library/react';

describe('LoadingButton', () => {
  it('renders children when not loading', () => {
    render(<LoadingButton>Click me</LoadingButton>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('renders loader when loading', () => {
    render(<LoadingButton loading>Loading...</LoadingButton>);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('disables button when loading', () => {
    render(<LoadingButton loading>Click me</LoadingButton>);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });

  it('respects height prop', () => {
    render(<LoadingButton height={60}>Click me</LoadingButton>);
    const button = screen.getByRole('button');
    expect(button).toHaveStyle({ height: '60px' });
  });

  it('renders with default height when not provided', () => {
    render(<LoadingButton>Click me</LoadingButton>);
    const button = screen.getByRole('button');
    expect(button).toHaveStyle({ height: '40px' });
  });
});
