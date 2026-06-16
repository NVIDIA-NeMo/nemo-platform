// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CopyButton } from '@studio/components/CopyButton';
import { render, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const textToCopy = 'Text that I want to copy';
const toastSuccessText = 'Successfully copied to clipboard!';
const toastErrorText = 'Error copying text to clipboard';

describe('CopyButton', () => {
  it('Copies text to clipboard on-click of the button', async () => {
    // `userEvent.setup()` stubs `window.navigator.clipboard` behind the scenes,
    // so we don't have to manually mock it.
    const user = userEvent.setup();

    render(<CopyButton text={textToCopy} />);

    const button = await screen.findByRole('button');
    await user.click(button);

    expect(await navigator.clipboard.readText()).toEqual(textToCopy);
    expect(await screen.findByText(toastSuccessText)).toBeInTheDocument();
  });

  it('Renders error toast if text fails to copy to clipboard', async () => {
    // Mock error with clipboard API
    vitest.spyOn(navigator.clipboard, 'writeText').mockRejectedValueOnce('Error copying text');

    const user = userEvent.setup();

    render(<CopyButton text={textToCopy} />);

    const button = await screen.findByRole('button');
    await user.click(button);

    expect(await screen.findByText(toastErrorText)).toBeInTheDocument();
  });
});
