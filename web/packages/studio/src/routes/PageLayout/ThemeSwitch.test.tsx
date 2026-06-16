// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ThemeSwitch } from '@studio/routes/PageLayout/ThemeSwitch';
import { render, screen, waitFor } from '@studio/tests/util/render';
import { UI_THEME } from '@studio/util/localStorage';
import userEvent from '@testing-library/user-event';

describe('ThemeSwitch', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(UI_THEME, '"light"');
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('Updates selected theme when switched and persists to localStorage', async () => {
    render(<ThemeSwitch />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Switch to dark theme/ })).toBeInTheDocument();
    });
    expect(window.localStorage.getItem(UI_THEME)).toBe('"light"');

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Switch to light theme/ })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(window.localStorage.getItem(UI_THEME)).toBe('"dark"');
    });
  });
});
