/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { ControlledCombobox } from '@nemo/common/src/components/form/ControlledCombobox/index';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

const ITEMS = ['email', 'ssn'];

interface SingleForm {
  label: string;
}
interface MultiForm {
  labels: string[];
}

const SingleHarness = ({
  freeForm,
  onValues,
}: {
  freeForm?: boolean;
  onValues: (value: string) => void;
}) => {
  const methods = useForm<SingleForm>({ defaultValues: { label: '' } });
  onValues(methods.watch('label'));
  return (
    <FormProvider {...methods}>
      <ControlledCombobox
        aria-label="Label"
        items={ITEMS}
        freeForm={freeForm}
        useControllerProps={{ name: 'label', control: methods.control }}
      />
    </FormProvider>
  );
};

const MultiHarness = ({
  freeForm,
  controlledInput,
  onValues,
}: {
  freeForm?: boolean;
  controlledInput?: boolean;
  onValues: (value: string[]) => void;
}) => {
  const methods = useForm<MultiForm>({ defaultValues: { labels: [] } });
  const [inputValue, setInputValue] = useState('');
  onValues(methods.watch('labels'));
  return (
    <FormProvider {...methods}>
      <ControlledCombobox
        kind="multiple"
        aria-label="Labels"
        items={ITEMS}
        freeForm={freeForm}
        {...(controlledInput ? { inputValue, onInputValueChange: setInputValue } : {})}
        useControllerProps={{ name: 'labels', control: methods.control }}
      />
      <output data-testid="typed">{controlledInput ? inputValue : ''}</output>
    </FormProvider>
  );
};

describe('ControlledCombobox', () => {
  it('writes typed text into a single-select field when freeForm is set', async () => {
    let value = '';
    render(<SingleHarness freeForm onValues={(next) => (value = next)} />);

    await userEvent.type(screen.getByRole('combobox', { name: 'Label' }), 'custom');

    await waitFor(() => expect(value).toBe('custom'));
  });

  it('never writes raw input into a multi-select field', async () => {
    let value: string[] = [];
    render(<MultiHarness freeForm onValues={(next) => (value = next)} />);

    await userEvent.type(screen.getByRole('combobox', { name: 'Labels' }), 'custom');

    expect(Array.isArray(value)).toBe(true);
    expect(value).toEqual([]);
  });

  it('surfaces typed text to the caller when the input is controlled', async () => {
    render(<MultiHarness controlledInput onValues={() => {}} />);

    await userEvent.type(screen.getByRole('combobox', { name: 'Labels' }), 'ice_cream');

    await waitFor(() => expect(screen.getByTestId('typed')).toHaveTextContent('ice_cream'));
  });

  it('adds typed text to a multi-select field on Enter', async () => {
    let value: string[] = [];
    render(<MultiHarness freeForm onValues={(next) => (value = next)} />);

    const input = screen.getByRole('combobox', { name: 'Labels' });
    await userEvent.type(input, 'ice_cream{Enter}');
    await waitFor(() => expect(value).toEqual(['ice_cream']));

    await userEvent.type(input, 'sprinkles{Enter}');
    await waitFor(() => expect(value).toEqual(['ice_cream', 'sprinkles']));
  });

  it('ignores Enter on blank or duplicate entries', async () => {
    let value: string[] = [];
    render(<MultiHarness freeForm onValues={(next) => (value = next)} />);

    const input = screen.getByRole('combobox', { name: 'Labels' });
    await userEvent.type(input, 'ice_cream{Enter}');
    await waitFor(() => expect(value).toEqual(['ice_cream']));

    await userEvent.type(input, '   {Enter}');
    await userEvent.type(input, 'ice_cream{Enter}');

    expect(value).toEqual(['ice_cream']);
  });

  it('does not add on Enter without freeForm', async () => {
    let value: string[] = [];
    render(<MultiHarness onValues={(next) => (value = next)} />);

    await userEvent.type(screen.getByRole('combobox', { name: 'Labels' }), 'ice_cream{Enter}');

    expect(value).toEqual([]);
  });

  it('still selects items in multi-select mode', async () => {
    let value: string[] = [];
    render(<MultiHarness onValues={(next) => (value = next)} />);

    await userEvent.click(screen.getByRole('combobox', { name: 'Labels' }));
    await userEvent.click(await screen.findByRole('option', { name: 'email' }));

    await waitFor(() => expect(value).toEqual(['email']));
  });
});
