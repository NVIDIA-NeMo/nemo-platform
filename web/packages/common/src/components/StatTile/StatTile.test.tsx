// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StatTile } from '@nemo/common/src/components/StatTile';
import { render, screen } from '@testing-library/react';

describe('StatTile', () => {
  it('renders the label and value', () => {
    render(<StatTile label="Final training loss" value="0.1234" />);

    expect(screen.getByText('Final training loss')).toBeInTheDocument();
    expect(screen.getByText('0.1234')).toBeInTheDocument();
  });

  it('renders the hint only when provided', () => {
    const { rerender } = render(
      <StatTile label="Final training loss" value="0.1234" hint="-0.05 from start" />
    );
    expect(screen.getByText('-0.05 from start')).toBeInTheDocument();

    rerender(<StatTile label="Final training loss" value="0.1234" />);
    expect(screen.queryByText('-0.05 from start')).not.toBeInTheDocument();
  });

  it('applies the success hint status class when specified', () => {
    render(
      <StatTile label="Final training loss" value="0.1234" hint="-0.05" hintStatus="success" />
    );

    expect(screen.getByText('-0.05')).toHaveClass(
      'text-[color:var(--text-color-feedback-success)]'
    );
  });

  it('applies the warning hint status class when specified', () => {
    render(
      <StatTile label="Truncation Rate" value="4.1%" hint="hit length limit" hintStatus="warning" />
    );

    expect(screen.getByText('hit length limit')).toHaveClass(
      'text-[color:var(--text-color-feedback-warning)]'
    );
  });

  it('applies the error hint status class when specified', () => {
    render(
      <StatTile label="Final validation loss" value="0.9876" hint="+0.05" hintStatus="error" />
    );

    expect(screen.getByText('+0.05')).toHaveClass('text-[color:var(--text-color-feedback-danger)]');
  });

  it('renders the label in the same muted tone as an unstatused hint', () => {
    render(<StatTile label="Learning Rate" value="1.00e-6" hint="at latest step" />);

    expect(screen.getByText('Learning Rate')).toHaveClass('text-placeholder');
    expect(screen.getByText('at latest step')).toHaveClass('text-placeholder');
  });
});
