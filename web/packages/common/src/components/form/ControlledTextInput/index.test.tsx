// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput/index';
import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('ControlledTextInput', () => {
  const user = userEvent.setup();
  it('should render a text input', () => {
    render(
      <FormWrapper>
        <ControlledTextInput useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('should render a disabled input', () => {
    render(
      <FormWrapper>
        <ControlledTextInput useControllerProps={{ name: 'testField' }} disabled />
      </FormWrapper>
    );
    expect(screen.getByRole('textbox')).toHaveAttribute('disabled');
  });

  it('should render a required input', () => {
    render(
      <FormWrapper>
        <ControlledTextInput useControllerProps={{ name: 'testField' }} required />
      </FormWrapper>
    );
    expect(screen.getByRole('textbox')).toHaveAttribute('required');
  });

  describe('masked', () => {
    it('renders a password input with a visibility toggle when `masked` is true', async () => {
      render(
        <FormWrapper>
          <ControlledTextInput
            useControllerProps={{ name: 'testField', defaultValue: 'sk-abc123' }}
            masked
          />
        </FormWrapper>
      );
      expect(screen.getByDisplayValue('sk-abc123')).toHaveAttribute('type', 'password');

      await user.click(screen.getByRole('button', { name: /show value/i }));
      expect(screen.getByDisplayValue('sk-abc123')).toHaveAttribute('type', 'text');
    });
  });

  describe('number input', () => {
    it('should render a number input', () => {
      render(
        <FormWrapper>
          <ControlledTextInput useControllerProps={{ name: 'testField' }} type="number" />
        </FormWrapper>
      );
      expect(screen.getByRole('spinbutton')).toBeInTheDocument();
    });
    it('should handle number input with empty value', async () => {
      render(
        <FormWrapper>
          <ControlledTextInput useControllerProps={{ name: 'testField' }} type="number" />
        </FormWrapper>
      );
      const input = screen.getByRole('spinbutton');
      await user.clear(input);
      expect(input.getAttribute('value')).toBeFalsy();
    });
    it.each([
      ['positive', '123'],
      ['negative', '-123'],
      ['decimal', '123.45'],
      ['scientific', '1.23e4'],
    ])('should handle number input with %s', async (_, value) => {
      render(
        <FormWrapper>
          <ControlledTextInput
            useControllerProps={{ name: 'testField', defaultValue: '' }}
            type="number"
          />
        </FormWrapper>
      );
      const input = screen.getByRole('spinbutton');
      await user.type(input, value);
      expect(input).toHaveValue(Number(value));
    });
  });
});
