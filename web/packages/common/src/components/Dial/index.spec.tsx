// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Dial } from '@nemo/common/src/components/Dial/index';
import { render, screen } from '@testing-library/react';

describe('Dial component', () => {
  beforeEach(() => {
    // Mock requestAnimationFrame to not actually animate in tests
    let rafId = 0;
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(() => {
      rafId++;
      return rafId;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should support percentage display', () => {
    render(<Dial value={85} displayValue="85%" color="green" />);

    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('should support score display', () => {
    render(<Dial value={92} displayValue="92/100" color="blue" />);

    expect(screen.getByText('92/100')).toBeInTheDocument();
  });

  it('should support metric display', () => {
    render(<Dial value={73.5} displayValue="73.5" color="orange" />);

    expect(screen.getByText('73.5')).toBeInTheDocument();
  });

  it('should support no data state', () => {
    render(<Dial value={0} displayValue="" color="gray" />);

    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('should support multiple dials with different configurations', () => {
    render(
      <div>
        <Dial value={50} displayValue="50%" color="blue" size="l" />
        <Dial value={75} displayValue="75%" color="green" size="m" />
        <Dial value={90} displayValue="90%" color="red" size="s" />
      </div>
    );

    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
  });

  it('should support evaluation metrics', () => {
    render(<Dial value={78.9} displayValue="78.9" color="var(--color-success)" />);

    expect(screen.getByText('78.9')).toBeInTheDocument();
  });

  it('should support loading state with empty display', () => {
    render(<Dial value={0} displayValue="" color="var(--color-neutral)" />);

    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
