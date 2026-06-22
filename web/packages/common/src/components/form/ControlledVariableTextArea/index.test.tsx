// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EditorView } from '@codemirror/view';
import { ControlledVariableTextArea } from '@nemo/common/src/components/form/ControlledVariableTextArea/index';
import { act, render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';

interface FormShape {
  content: string;
}

function Harness({ initial = '' }: { initial?: string }) {
  const { control, watch } = useForm<FormShape>({ defaultValues: { content: initial } });
  const value = watch('content');
  return (
    <>
      <ControlledVariableTextArea
        useControllerProps={{ control, name: 'content' }}
        formFieldProps={{ name: 'content', slotLabel: 'Prompt' }}
        attributes={{ TextAreaElement: { 'data-testid': 'editor' } }}
      />
      <output data-testid="value">{value}</output>
    </>
  );
}

describe('ControlledVariableTextArea', () => {
  it('writes through to the form value', () => {
    // userEvent.keyboard does not trigger CodeMirror's onChange under happy-dom
    // (CodeMirror uses contenteditable + its own input handling). We drive the
    // editor via the EditorView API instead — the same pattern used in the
    // VariableTextArea unit tests.
    render(<Harness />);
    // eslint-disable-next-line testing-library/no-node-access -- CodeMirror DOM structure assertion
    const cmEditor = screen.getByTestId('editor').closest('.cm-editor');
    const view = EditorView.findFromDOM(cmEditor as HTMLElement);
    expect(view).not.toBeNull();

    act(() => {
      view!.dispatch({
        changes: { from: 0, to: 0, insert: 'hi' },
        selection: { anchor: 2 },
      });
    });

    expect(screen.getByTestId('value')).toHaveTextContent('hi');
  });

  it('renders the form-field label', () => {
    render(<Harness />);
    expect(screen.getByText('Prompt')).toBeInTheDocument();
  });
});
