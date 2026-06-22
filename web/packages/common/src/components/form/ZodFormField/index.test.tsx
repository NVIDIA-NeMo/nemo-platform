// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ZodFormField } from '@nemo/common/src/components/form/ZodFormField/index';
import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { render, screen } from '@testing-library/react';
import { z } from 'zod';

describe('ZodFormField', () => {
  it('renders text input for ZodString', () => {
    const schema = z.string();
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('renders textarea for ZodString with maxLength > 100', () => {
    const schema = z.string().max(150);
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveAttribute('rows'); // textarea has rows attribute
  });

  it('renders select for ZodString with enum values', async () => {
    const schema = z.enum(['option1', 'option2', 'option3']);
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(await screen.findByRole('combobox')).toBeInTheDocument();
  });

  it('renders number input for ZodNumber', () => {
    const schema = z.number();
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(screen.getByRole('spinbutton')).toBeInTheDocument();
  });

  it('renders slider for ZodNumber with min, max, step', () => {
    const schema = z.number();
    render(
      <FormWrapper>
        <ZodFormField
          schema={schema}
          min={0}
          max={100}
          step={1}
          useControllerProps={{ name: 'testField' }}
        />
      </FormWrapper>
    );

    expect(screen.getByRole('slider')).toBeInTheDocument();
  });

  it('renders switch for ZodBoolean', () => {
    const schema = z.boolean();
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('renders combobox for ZodArray of strings', () => {
    const schema = z.array(z.string());
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('renders text input for ZodArray of non-strings', () => {
    const schema = z.array(z.number());
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('renders select for ZodUnion', async () => {
    const schema = z.union([z.literal('option1'), z.literal('option2')]);
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(await screen.findByRole('combobox')).toBeInTheDocument();
  });

  it('renders select for ZodEnum', async () => {
    const schema = z.enum(['enum1', 'enum2', 'enum3']);
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(await screen.findByRole('combobox')).toBeInTheDocument();
  });

  it('renders read-only input for ZodLiteral', () => {
    const schema = z.literal('fixed-value');
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    const input = screen.getByRole('textbox');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('disabled');
    expect(input).toHaveValue('fixed-value');
  });

  it('renders nested fields for ZodObject', () => {
    const schema = z.object({
      name: z.string(),
      age: z.number(),
    });
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    // Should render nested fields
    expect(screen.getByText('Nested object field: testField')).toBeInTheDocument();
  });

  it('renders fallback for unsupported types', () => {
    const schema = z.any();
    render(
      <FormWrapper>
        <ZodFormField schema={schema} useControllerProps={{ name: 'testField' }} />
      </FormWrapper>
    );

    expect(screen.getByText('Unsupported field type: ZodAny')).toBeInTheDocument();
  });
});
