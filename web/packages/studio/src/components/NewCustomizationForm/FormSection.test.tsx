// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import { render, screen } from '@testing-library/react';

describe('FormSection', () => {
  it('should render title and children', () => {
    render(
      <FormSection title="Test Title">
        <div data-testid="child">Child content</div>
      </FormSection>
    );

    expect(screen.getByText('Test Title')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('should render description when provided', () => {
    render(
      <FormSection title="Title" description="A helpful description">
        <div>Content</div>
      </FormSection>
    );

    expect(screen.getByText('A helpful description')).toBeInTheDocument();
  });

  it('should not render description when omitted', () => {
    render(
      <FormSection title="Title">
        <div>Content</div>
      </FormSection>
    );

    const descriptions = screen.queryAllByText((_, element) =>
      element?.tagName === 'P' || element?.getAttribute('kind') === 'body/regular/md' ? true : false
    );
    expect(descriptions).toHaveLength(0);
  });

  it('should render ReactNode description with links', () => {
    render(
      <FormSection
        title="Title"
        description={
          <>
            Visit <a href="https://example.com">the docs</a>.
          </>
        }
      >
        <div>Content</div>
      </FormSection>
    );

    expect(screen.getByText('the docs')).toBeInTheDocument();
  });
});
