// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SpanPayloadBlock } from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadBlock';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';

describe('SpanPayloadBlock', () => {
  it('renders small payloads immediately', () => {
    renderRoute(<SpanPayloadBlock value="small payload" emptyMessage="No payload" />);

    expect(screen.queryByLabelText('Rendering payload')).not.toBeInTheDocument();
    expect(screen.getByText('small payload')).toBeInTheDocument();
  });

  it('shows a loader before rendering large payloads', async () => {
    const payload = 'x'.repeat(20_001);

    renderRoute(<SpanPayloadBlock value={payload} emptyMessage="No payload" />);

    expect(screen.getByLabelText('Rendering payload')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByLabelText('Rendering payload')).not.toBeInTheDocument()
    );
    expect(screen.getByTestId('nv-code-snippet-code')).toHaveTextContent(payload);
  });

  it('renders the empty state for blank payloads', () => {
    renderRoute(<SpanPayloadBlock value="   " emptyMessage="No payload" />);

    expect(screen.getByText('No payload')).toBeInTheDocument();
  });
});
