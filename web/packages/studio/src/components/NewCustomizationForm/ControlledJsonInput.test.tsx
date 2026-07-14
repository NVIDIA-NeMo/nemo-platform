// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledJsonInput } from '@studio/components/NewCustomizationForm/ControlledJsonInput';
import { act, render, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { FC } from 'react';
import { FormProvider, useForm, useWatch } from 'react-hook-form';

interface FormShape {
  cfg?: unknown;
}

const Spy: FC = () => {
  const value = useWatch<FormShape>({ name: 'cfg' });
  return <div data-testid="value">{value === undefined ? 'UNDEFINED' : JSON.stringify(value)}</div>;
};

const Harness: FC<{ onReady?: (setValue: (v: unknown) => void) => void }> = ({ onReady }) => {
  const methods = useForm<FormShape>({ defaultValues: { cfg: undefined } });
  onReady?.((v) => methods.setValue('cfg', v));
  return (
    <FormProvider {...methods}>
      <ControlledJsonInput
        useControllerProps={{ name: 'cfg', control: methods.control }}
        formFieldProps={{ slotLabel: 'Config' }}
      />
      <Spy />
    </FormProvider>
  );
};

const typeInto = async (user: ReturnType<typeof userEvent.setup>, text: string) => {
  const box = screen.getByRole('textbox', { name: /config/i });
  await user.clear(box);
  await user.type(box, text);
  return box;
};

describe('ControlledJsonInput', () => {
  it('writes parsed JSON objects to the field', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    // `[` and `{` are special chars for user.type; escape by wrapping in braces.
    await typeInto(user, '{{ "a": 1 }');
    expect(screen.getByTestId('value')).toHaveTextContent('{"a":1}');
  });

  it('parses a bare JSON string (for str-or-object fields like deployment_config)', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await typeInto(user, '"my-config"');
    expect(screen.getByTestId('value')).toHaveTextContent('my-config');
  });

  it('clears the field to undefined when emptied', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await typeInto(user, '"x"');
    expect(screen.getByTestId('value')).toHaveTextContent('x');
    await user.clear(screen.getByRole('textbox', { name: /config/i }));
    expect(screen.getByTestId('value')).toHaveTextContent('UNDEFINED');
  });

  it('shows an error and does not update the field on invalid JSON', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await typeInto(user, '{{ not json');
    expect(screen.getByText('Invalid JSON')).toBeInTheDocument();
    expect(screen.getByTestId('value')).toHaveTextContent('UNDEFINED');
  });

  it('resyncs the text box when the field is changed externally', async () => {
    let setValue: (v: unknown) => void = () => {};
    render(<Harness onReady={(fn) => (setValue = fn)} />);

    // The box starts empty; an external setValue must be reflected in the text.
    await act(async () => setValue({ b: 2 }));
    const box = screen.getByRole('textbox', { name: /config/i });
    await waitFor(() => expect(box).toHaveValue(JSON.stringify({ b: 2 }, null, 2)));

    // Clearing the field externally empties the box.
    await act(async () => setValue(undefined));
    await waitFor(() => expect(box).toHaveValue(''));
  });
});
