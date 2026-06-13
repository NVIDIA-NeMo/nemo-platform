// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { render, waitFor } from '@testing-library/react';

describe('AccessibleTitle', () => {
  it('renders with a default title if none given', async () => {
    render(<AccessibleTitle>hello world</AccessibleTitle>);
    await waitFor(() => {
      expect(document.title).toEqual('Studio');
    });
  });

  it('renders with a custom title provided', async () => {
    render(<AccessibleTitle title="Hello world">hello world</AccessibleTitle>);
    await waitFor(() => {
      expect(document.title).toEqual('Hello world - Studio');
    });
  });

  it('changes titles upon render change', async () => {
    render(<AccessibleTitle title="Hello world">hello world</AccessibleTitle>);
    await waitFor(() => {
      expect(document.title).toEqual('Hello world - Studio');
    });
    render(<AccessibleTitle title="Goodbye">goodbye</AccessibleTitle>);
    await waitFor(() => {
      expect(document.title).toEqual('Goodbye - Studio');
    });
  });
});
