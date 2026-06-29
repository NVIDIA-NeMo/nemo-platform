// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import { fireEvent, render, screen } from '@testing-library/react';

const items = [
  {
    value: 'one',
    slotLabel: 'Section one',
    slotEnd: <span>meta-one</span>,
    slotContent: <p>Body one</p>,
  },
  {
    value: 'two',
    slotLabel: 'Section two',
    slotContent: <p>Body two</p>,
  },
];

describe('IntakeAccordion', () => {
  it('renders each item trigger label and end slot', () => {
    render(<IntakeAccordion items={items} />);

    expect(screen.getByText('Section one')).toBeInTheDocument();
    expect(screen.getByText('Section two')).toBeInTheDocument();
    expect(screen.getByText('meta-one')).toBeInTheDocument();
  });

  it('reveals an item body when its trigger is opened (uncontrolled)', () => {
    render(<IntakeAccordion items={items} />);

    fireEvent.click(screen.getByText('Section one'));

    expect(screen.getByText('Body one')).toBeVisible();
  });

  it('opens items listed in defaultValue', () => {
    render(<IntakeAccordion items={items} defaultValue={['two']} />);

    expect(screen.getByText('Body two')).toBeVisible();
  });

  it('drives open state and reports changes when controlled', () => {
    const onValueChange = vi.fn();
    render(<IntakeAccordion items={items} value={['one']} onValueChange={onValueChange} />);

    expect(screen.getByText('Body one')).toBeVisible();

    fireEvent.click(screen.getByText('Section two'));

    expect(onValueChange).toHaveBeenCalledWith(expect.arrayContaining(['one', 'two']));
  });
});
