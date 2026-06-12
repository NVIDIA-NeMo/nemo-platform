// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  TableHeaderButton,
  type TableHeaderButtonProps,
} from '@nemo/common/src/components/TableHeaderButton/index';
import { render, screen } from '@testing-library/react';

describe('TableHeaderButton', () => {
  const defaultProps: TableHeaderButtonProps = {
    children: 'Test Button',
    onClick: vi.fn(),
  };

  describe('Component Rendering', () => {
    it('renders button with correct content', () => {
      render(<TableHeaderButton {...defaultProps} />);

      expect(screen.getByRole('button', { name: 'Test Button' })).toBeInTheDocument();
    });

    it('renders with custom className', () => {
      const customClass = 'custom-test-class';
      render(<TableHeaderButton {...defaultProps} className={customClass} />);

      const button = screen.getByRole('button');
      expect(button).toHaveClass(customClass);
    });
  });
});
