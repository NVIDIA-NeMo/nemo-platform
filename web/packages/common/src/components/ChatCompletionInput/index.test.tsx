/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { ChatCompletionInput } from '@nemo/common/src/components/ChatCompletionInput';
import {
  defaultChatCompletionMessageRow,
  type ChatCompletionMessageRowValues,
} from '@nemo/common/src/components/ChatCompletionInput/schema';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormProvider, useFieldArray, useForm, type Path } from 'react-hook-form';

type FormValues = {
  messages: ChatCompletionMessageRowValues[];
};

function TestForm({
  onDuplicate,
  allowRemove = true,
}: {
  onDuplicate?: (index: number) => void;
  allowRemove?: boolean;
}) {
  const methods = useForm<FormValues>({
    defaultValues: {
      messages: [
        { ...defaultChatCompletionMessageRow(), content: 'First message' },
        { ...defaultChatCompletionMessageRow(), role: 'assistant', content: 'Second' },
      ],
    },
  });

  const { fields, move, remove, insert } = useFieldArray({
    control: methods.control,
    name: 'messages',
  });

  return (
    <FormProvider {...methods}>
      {fields.map((field, index) => (
        <ChatCompletionInput<FormValues>
          key={field.id}
          control={methods.control}
          name={`messages.${index}`}
          fieldArrayLength={fields.length}
          dataTestId={`chat-completion-row-${index}`}
          onMoveUp={index > 0 ? () => move(index, index - 1) : undefined}
          onMoveDown={index < fields.length - 1 ? () => move(index, index + 1) : undefined}
          onDuplicate={
            onDuplicate
              ? () => onDuplicate(index)
              : () => {
                  const rowPath = `messages.${index}` as Path<FormValues>;
                  const row = methods.getValues(rowPath) as ChatCompletionMessageRowValues;
                  insert(index + 1, { ...row });
                }
          }
          onRemove={() => remove(index)}
          allowRemove={allowRemove && fields.length > 1}
          footer={<span data-testid={`footer-${index}`}>Footer {index}</span>}
        />
      ))}
    </FormProvider>
  );
}

describe('ChatCompletionInput', () => {
  it('renders role, expandable body, footer, and action tooltips', async () => {
    const user = userEvent.setup();
    render(<TestForm />);

    expect(screen.getByText('First message')).toBeInTheDocument();
    expect(screen.getByTestId('footer-0')).toHaveTextContent('Footer 0');

    const firstRow = screen.getByTestId('chat-completion-row-0');
    await user.click(within(firstRow).getByRole('button', { name: 'Collapse message' }));

    expect(screen.queryByDisplayValue('First message')).not.toBeInTheDocument();
    expect(screen.getByText('First message')).toBeInTheDocument();

    await user.hover(within(firstRow).getByRole('button', { name: 'Move down' }));
  });

  it('renders the variable-aware editor when `variables` is provided', async () => {
    function Harness() {
      const methods = useForm({
        defaultValues: { messages: [{ role: 'user', content: '{{input}}', expanded: true }] },
      });
      return (
        <FormProvider {...methods}>
          <ChatCompletionInput
            control={methods.control}
            name="messages.0"
            variables={[{ name: 'input' }]}
          />
        </FormProvider>
      );
    }
    render(<Harness />);
    // CodeMirror renders a div[role=textbox] rather than a <textarea>
    await waitFor(() => {
      expect(screen.getByTestId('chat-completion-message-content').tagName).toBe('DIV');
    });
    expect(screen.getByText('{{input}}')).toBeInTheDocument();
  });

  it('uses the plain ControlledTextArea when `variables` is omitted', async () => {
    function Harness() {
      const methods = useForm({
        defaultValues: { messages: [{ role: 'user', content: 'hi', expanded: true }] },
      });
      return (
        <FormProvider {...methods}>
          <ChatCompletionInput control={methods.control} name="messages.0" />
        </FormProvider>
      );
    }
    render(<Harness />);
    // Plain ControlledTextArea renders a <textarea>
    await waitFor(() => {
      expect(screen.getByTestId('chat-completion-message-content').tagName).toBe('TEXTAREA');
    });
  });

  it('passes insertVariable to function-shaped footer; selecting inserts a token', async () => {
    const user = userEvent.setup();
    function Harness() {
      const methods = useForm({
        defaultValues: { messages: [{ role: 'user', content: '', expanded: true }] },
      });
      const value = methods.watch('messages.0.content');
      return (
        <FormProvider {...methods}>
          <ChatCompletionInput
            control={methods.control}
            name="messages.0"
            variables={[{ name: 'input' }]}
            footer={({ insertVariable }) => (
              <button type="button" onClick={() => insertVariable('input')}>
                insert
              </button>
            )}
          />
          <output data-testid="value">{value}</output>
        </FormProvider>
      );
    }
    render(<Harness />);
    await user.click(screen.getByRole('button', { name: 'insert' }));
    expect(screen.getByTestId('value')).toHaveTextContent('{{input}}');
  });

  it('duplicate inserts a copy via field array', async () => {
    function SingleRowDupForm() {
      const methods = useForm<FormValues>({
        defaultValues: {
          messages: [{ ...defaultChatCompletionMessageRow(), content: 'Solo row' }],
        },
      });
      const { fields, insert } = useFieldArray({ control: methods.control, name: 'messages' });
      return (
        <FormProvider {...methods}>
          {fields.map((field, index) => (
            <ChatCompletionInput<FormValues>
              key={field.id}
              control={methods.control}
              name={`messages.${index}`}
              fieldArrayLength={fields.length}
              dataTestId={`chat-completion-row-${index}`}
              onDuplicate={() => {
                const rowPath = `messages.${index}` as Path<FormValues>;
                const row = methods.getValues(rowPath) as ChatCompletionMessageRowValues;
                insert(index + 1, { ...row });
              }}
            />
          ))}
        </FormProvider>
      );
    }

    const user = userEvent.setup();
    render(<SingleRowDupForm />);

    const row = screen.getByTestId('chat-completion-row-0');
    await user.hover(row);
    await user.click(within(row).getByRole('button', { name: 'Duplicate message' }));

    await waitFor(() => {
      expect(screen.getAllByTestId('chat-completion-message-content')).toHaveLength(2);
    });
    const areas = screen.getAllByTestId('chat-completion-message-content');
    expect(areas[0]).toHaveValue('Solo row');
    expect(areas[1]).toHaveValue('Solo row');
  });
});
