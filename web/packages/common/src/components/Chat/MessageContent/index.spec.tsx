// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import { render, screen } from '@testing-library/react';

describe('MessageContent', () => {
  it('renders inline code with light and dark grey backgrounds', () => {
    render(<MessageContent content="Run `pnpm test` after editing." />);

    expect(screen.getByText('pnpm test')).toHaveClass(
      'bg-gray-050',
      'dark:bg-gray-900',
      'font-mono'
    );
  });
});
