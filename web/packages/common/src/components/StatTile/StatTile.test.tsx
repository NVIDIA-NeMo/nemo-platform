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

  it('renders the trailing label only when provided', () => {
    const { rerender } = render(
      <StatTile label="gen_kl_error" value="5.4e-4" trailingLabel="ok" />
    );
    expect(screen.getByText('ok')).toBeInTheDocument();

    rerender(<StatTile label="gen_kl_error" value="5.4e-4" />);
    expect(screen.queryByText('ok')).not.toBeInTheDocument();
  });

  it('statuses the trailing label independently of the hint', () => {
    render(
      <StatTile
        label="approx_entropy"
        value="0.31"
        trailingLabel="falling"
        trailingLabelStatus="warning"
        hint="entropy collapse risk"
      />
    );

    expect(screen.getByText('falling')).toHaveClass(
      'text-[color:var(--text-color-feedback-warning)]'
    );
    expect(screen.getByText('entropy collapse risk')).toHaveClass('text-placeholder');
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

  it('drops its surrounding surface when not bordered', () => {
    const { rerender } = render(<StatTile label="Duration" value="00:01:38" />);
    expect(screen.getByTestId('stat-tile-surface')).toBeInTheDocument();

    rerender(<StatTile label="Duration" value="00:01:38" bordered={false} />);
    expect(screen.queryByTestId('stat-tile-surface')).not.toBeInTheDocument();
    expect(screen.getByText('Duration')).toBeInTheDocument();
    expect(screen.getByText('00:01:38')).toBeInTheDocument();
  });

  it('renders the label in the same muted tone as an unstatused hint', () => {
    render(<StatTile label="Learning Rate" value="1.00e-6" hint="at latest step" />);

    expect(screen.getByText('Learning Rate')).toHaveClass('text-placeholder');
    expect(screen.getByText('at latest step')).toHaveClass('text-placeholder');
  });
});
