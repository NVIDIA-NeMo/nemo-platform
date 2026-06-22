// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DocumentationButton } from '@studio/components/DocumentationButton';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

describe('DocumentationButton', () => {
  it('renders with documentation text', () => {
    render(
      <BrowserRouter>
        <DocumentationButton href="https://docs.example.com" />
      </BrowserRouter>
    );

    expect(screen.getByRole('link', { name: /documentation/i })).toBeInTheDocument();
  });

  it('opens link in new tab with correct attributes', () => {
    render(
      <BrowserRouter>
        <DocumentationButton href="https://docs.example.com" />
      </BrowserRouter>
    );

    const link = screen.getByRole('link', { name: /documentation/i });
    expect(link).toHaveAttribute('href', 'https://docs.example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});
