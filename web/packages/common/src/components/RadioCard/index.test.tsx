// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RadioGroupRoot } from '@nvidia/foundations-react-core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { RadioCard } from '.';

const renderGroup = (onValueChange: () => void, showIndicator?: boolean) => {
  render(
    <RadioGroupRoot name="test-group" value="a" onValueChange={onValueChange}>
      <RadioCard value="a" label="Option A" description="First" showIndicator={showIndicator} />
      <RadioCard value="b" label="Option B" description="Second" showIndicator={showIndicator} />
    </RadioGroupRoot>
  );
};

describe('RadioCard', () => {
  it('Renders a radio per card with its label and description by default', () => {
    renderGroup(vi.fn());

    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: 'Option A' })).toBeChecked();
    expect(screen.getByText('First')).toBeInTheDocument();
  });

  // The hidden indicator must stay in the DOM: four studio suites locate these
  // cards with getByRole('radio').
  it('Keeps the radio input queryable and operable when showIndicator is false', async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    renderGroup(onValueChange, false);

    const optionB = screen.getByRole('radio', { name: 'Option B' });
    expect(optionB).toBeInTheDocument();
    expect(optionB).not.toBeChecked();

    await user.click(screen.getByText('Option B'));

    expect(onValueChange).toHaveBeenCalledWith('b');
  });
});
