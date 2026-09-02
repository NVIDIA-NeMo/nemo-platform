// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TraceDetailLayout } from '@studio/components/IntakeDetail/TraceDetailLayout';
import { render, screen } from '@studio/tests/util/render';
import { fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('TraceDetailLayout', () => {
  it('resizes the trajectory sidebar without allowing it below its original width', async () => {
    const user = userEvent.setup();
    render(<TraceDetailLayout navigation="Trajectory">Details</TraceDetailLayout>);

    const sidebar = screen.getByTestId('trace-trajectory-sidebar');
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      bottom: 600,
      height: 600,
      left: 0,
      right: 1000,
      top: 0,
      width: 1000,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    const getComputedStyle = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element, pseudoElement) => {
      const styles = getComputedStyle(element, pseudoElement);
      Object.defineProperty(styles, 'columnGap', { configurable: true, value: '16px' });
      return styles;
    });

    const resizeHandle = screen.getByRole('separator', {
      name: 'Resize trace trajectory sidebar',
    });
    fireEvent.mouseDown(resizeHandle);
    fireEvent.mouseMove(window, { clientX: 500 });
    fireEvent.mouseUp(window);

    expect(sidebar).toHaveStyle({ width: '500px' });
    expect(resizeHandle).toHaveAttribute('aria-valuenow', '500');
    expect(resizeHandle).toHaveAttribute('aria-valuemax', '664');

    resizeHandle.focus();
    await user.keyboard('{End}');
    expect(sidebar).toHaveStyle({ width: '664px' });

    await user.keyboard('{Home}');
    expect(sidebar).toHaveStyle({ width: '288px' });

    fireEvent.mouseDown(resizeHandle);
    fireEvent.mouseMove(window, { clientX: 100 });
    fireEvent.mouseUp(window);
    expect(sidebar).toHaveStyle({ width: '288px' });
  });
});
