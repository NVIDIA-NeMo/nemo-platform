// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NotFound } from '@studio/components/Layouts/NotFound/index';
import { render, screen } from '@studio/tests/util/render';

describe('NotFound', () => {
  it('renders the default message', () => {
    render(<NotFound />);

    expect(screen.getByText('404 Error')).toBeInTheDocument();
    expect(screen.getByText("Even AI can't find this page!")).toBeInTheDocument();
    expect(
      screen.getByText(
        "If you're logged in, this might be a permissions issue. Check with your Org or Team Admin. Otherwise, you can return to your previous screen by clicking the link below."
      )
    ).toBeInTheDocument();
  });

  it('renders custom message', () => {
    render(
      <NotFound header="Custom Header" subheader="Custom Subheader" message="Custom Message" />
    );

    expect(screen.getByText('Custom Header')).toBeInTheDocument();
    expect(screen.getByText('Custom Subheader')).toBeInTheDocument();
    expect(screen.getByText('Custom Message')).toBeInTheDocument();
  });
});
