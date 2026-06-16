// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ValueWithLabel } from '@studio/components/ValueWithLabel';
import { EMPTY_FIELD_VALUE } from '@studio/constants/constants';
import { render, screen } from '@testing-library/react';

describe('ValueWithLabel', () => {
  it('should render a label', () => {
    const label = 'Test';
    const value = 'Value';
    render(<ValueWithLabel label={label} value={value} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByText(value)).toBeInTheDocument();
  });

  it('should render an empty value', () => {
    const label = 'Test';
    render(<ValueWithLabel label={label} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByText(EMPTY_FIELD_VALUE)).toBeInTheDocument();
  });

  it('should render a loading state', () => {
    const label = 'Test';
    render(<ValueWithLabel label={label} loading />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByTestId('nv-skeleton')).toBeInTheDocument();
  });
});
