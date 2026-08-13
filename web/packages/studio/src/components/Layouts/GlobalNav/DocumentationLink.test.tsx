// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DocumentationLink } from '@studio/components/Layouts/GlobalNav/DocumentationLink';
import { LINK_DOCS_STUDIO } from '@studio/constants/links';
import { render, screen } from '@studio/tests/util/render';

describe('DocumentationLink', () => {
  it('links to the Studio documentation in a new tab', () => {
    render(<DocumentationLink />);

    const link = screen.getByRole('link', { name: 'Documentation' });
    expect(link).toHaveAttribute('href', LINK_DOCS_STUDIO);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});
