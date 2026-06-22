/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { MappingFields } from '@nemo/common/src/components/form/MappingFields/index';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormProvider, useForm } from 'react-hook-form';

type FormValues = {
  mappings: Array<{ key: string; value?: string }>;
};

describe('MappingFields', () => {
  const mockSchema = {
    prompt: 'string',
    response: 'string',
    metadata: 'object',
  };

  const defaultValues: FormValues = {
    mappings: [
      { key: 'prompt', value: '{{{prompt}}}' },
      { key: 'response', value: '{{{response}}}' },
    ],
  };

  const FormTestComponent = (
    props: {
      disabled?: boolean;
      formDisabled?: boolean;
      schema?: Record<string, unknown>;
      defaultFormValues?: FormValues;
    } = {}
  ) => {
    const methods = useForm<FormValues>({
      defaultValues: props.defaultFormValues ?? defaultValues,
      mode: 'onChange',
      disabled: props.formDisabled,
    });

    return (
      <FormProvider {...methods}>
        <MappingFields
          control={methods.control}
          name="mappings"
          schema={props.schema ?? mockSchema}
          disabled={props.disabled}
        />
      </FormProvider>
    );
  };

  describe('Rendering', () => {
    it('should render mapping fields when schema is provided', async () => {
      render(<FormTestComponent />);

      await waitFor(() => {
        expect(screen.getAllByRole('combobox').length).toBe(8);
      });

      const comboboxes = screen.getAllByRole('combobox');
      const promptCombobox = comboboxes.find((cb) => cb.getAttribute('value') === 'prompt')!;
      const promptValueCombobox = comboboxes.find(
        (cb) => cb.getAttribute('value') === '{{{prompt}}}'
      )!;
      const responseCombobox = comboboxes.find((cb) => cb.getAttribute('value') === 'response')!;
      const responseValueCombobox = comboboxes.find(
        (cb) => cb.getAttribute('value') === '{{{response}}}'
      )!;
      expect(promptCombobox).toBeInTheDocument();
      expect(promptValueCombobox).toBeInTheDocument();
      expect(responseCombobox).toBeInTheDocument();
      expect(responseValueCombobox).toBeInTheDocument();

      expect(screen.getByText('Key')).toBeInTheDocument();
      expect(screen.getByText('Value')).toBeInTheDocument();

      expect(screen.queryByRole('button', { name: /add column/i })).not.toBeInTheDocument();

      const removeRowButtons = screen.getAllByRole('button', { name: 'Remove row' });
      expect(removeRowButtons[removeRowButtons.length - 1]).toBeDisabled();
      expect(removeRowButtons[0]).not.toBeDisabled();
    });

    it('should render with disabled state', async () => {
      render(<FormTestComponent disabled />);

      await waitFor(() => {
        expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0);
      });
      for (const btn of screen.getAllByRole('button', { name: 'Remove row' })) {
        expect(btn).toBeDisabled();
      }
    });

    it('should disable fields and remove buttons when the form is disabled', async () => {
      render(<FormTestComponent formDisabled />);

      await waitFor(() => {
        expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0);
      });
      for (const cb of screen.getAllByRole('combobox')) {
        expect(cb).toBeDisabled();
      }
      for (const btn of screen.getAllByRole('button', { name: 'Remove row' })) {
        expect(btn).toBeDisabled();
      }
    });
  });

  describe('Schema', () => {
    it('should populate fields from schema keys', async () => {
      render(<FormTestComponent />);
      const comboboxes = await screen.findAllByRole('combobox');
      const promptCombobox = comboboxes.find((cb) => cb.getAttribute('value') === 'prompt')!;
      const promptValueCombobox = comboboxes.find(
        (cb) => cb.getAttribute('value') === '{{{prompt}}}'
      )!;
      const metadataCombobox = comboboxes.find((cb) => cb.getAttribute('value') === 'metadata')!;
      const metadataValueCombobox = comboboxes.find(
        (cb) => cb.getAttribute('value') === '{{{metadata}}}'
      )!;

      expect(promptCombobox).toBeInTheDocument();
      expect(promptValueCombobox).toBeInTheDocument();
      expect(metadataCombobox).toBeInTheDocument();
      expect(metadataValueCombobox).toBeInTheDocument();
    });

    it('should update fields when schema keys change', async () => {
      const { rerender } = render(<FormTestComponent schema={mockSchema} />);
      await screen.findAllByRole('combobox');

      const newSchema = { question: 'string', answer: 'string' };
      rerender(<FormTestComponent schema={newSchema} />);

      const rerenderedComboboxes = await screen.findAllByRole('combobox');
      const questionCombobox = rerenderedComboboxes.find(
        (cb) => cb.getAttribute('value') === 'question'
      )!;
      const questionValueCombobox = rerenderedComboboxes.find(
        (cb) => cb.getAttribute('value') === '{{{question}}}'
      )!;

      expect(questionCombobox).toBeInTheDocument();
      expect(questionValueCombobox).toBeInTheDocument();
      expect(
        rerenderedComboboxes.find((cb) => cb.getAttribute('value') === 'prompt')
      ).toBeUndefined();
    });
  });

  describe('User interactions', () => {
    it('should append a blank row when the user types in the trailing empty key field', async () => {
      const user = userEvent.setup();
      render(<FormTestComponent />);

      await waitFor(() => {
        expect(screen.getAllByRole('combobox').length).toBe(8);
      });

      const comboboxes = screen.getAllByRole('combobox');
      const lastKeyCombobox = comboboxes[comboboxes.length - 2]!;
      expect(lastKeyCombobox.getAttribute('value')).toBe('');
      await user.type(lastKeyCombobox, 'n');

      await waitFor(() => {
        expect(screen.getAllByRole('combobox').length).toBe(10);
      });
    });

    it('should update field values when user types', async () => {
      const user = userEvent.setup();
      render(<FormTestComponent />);
      await screen.findAllByRole('combobox');
      const comboboxes = screen.getAllByRole('combobox');
      const keyCombobox = comboboxes.find((cb) => cb.getAttribute('value') === 'prompt')!;
      await user.clear(keyCombobox);
      await user.type(keyCombobox, 'newKey');

      expect(keyCombobox).toHaveValue('newKey');
    });
  });

  describe('Edge cases', () => {
    it('should handle empty schema', async () => {
      render(<FormTestComponent schema={{}} />);

      await waitFor(() => {
        expect(screen.getAllByRole('textbox').length).toBe(2);
      });
      expect(screen.queryByDisplayValue('prompt')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Remove row' })).toBeDisabled();
    });
  });

  describe('Free-form rows (no schema)', () => {
    it('should not overwrite rows when schema is omitted', async () => {
      const FreeFormHarness = () => {
        const methods = useForm<FormValues>({
          defaultValues,
          mode: 'onChange',
        });
        return (
          <FormProvider {...methods}>
            <MappingFields control={methods.control} name="mappings" />
          </FormProvider>
        );
      };

      render(<FreeFormHarness />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('prompt')).toBeInTheDocument();
      });
      expect(screen.getByDisplayValue('{{{prompt}}}')).toBeInTheDocument();
    });
  });
});
