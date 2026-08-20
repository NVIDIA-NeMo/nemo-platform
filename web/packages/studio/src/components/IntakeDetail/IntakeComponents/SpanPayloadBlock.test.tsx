// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SpanPayloadBlock } from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadBlock';
import { SpanPayloadViewMode } from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadRendererControl';
import { act, fireEvent, renderRoute, screen, waitFor } from '@studio/tests/util/render';
import { useState } from 'react';

describe('SpanPayloadBlock', () => {
  it('renders small payloads immediately', () => {
    renderRoute(<SpanPayloadBlock value="small payload" emptyMessage="No payload" />);

    expect(screen.queryByLabelText('Rendering payload')).not.toBeInTheDocument();
    expect(screen.getByText('small payload')).toBeInTheDocument();
  });

  it('renders Markdown as formatted document content', () => {
    renderRoute(
      <SpanPayloadBlock
        value={'# Trace heading\n\n- first item\n- second item'}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.markdown}
      />
    );

    expect(screen.getByRole('heading', { name: 'Trace heading' })).toBeInTheDocument();
    expect(screen.getByRole('list')).toHaveTextContent('first item');
    expect(screen.getByRole('list')).toHaveTextContent('second item');
  });

  it('pretty-prints valid JSON payloads', () => {
    renderRoute(
      <SpanPayloadBlock
        value={'{"nested":{"enabled":true},"items":[1,2]}'}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.json}
      />
    );

    const code = screen.getByTestId('nv-code-snippet-code');
    expect(code).toHaveTextContent('"nested":');
    expect(code).toHaveTextContent('"enabled": true');
    expect(code).toHaveTextContent('"items":');
  });

  it('preserves JSON numeric tokens that exceed JavaScript integer precision', () => {
    renderRoute(
      <SpanPayloadBlock
        value={'{"trace_id":9007199254740993123456789,"negative_zero":-0,"huge":1e+400}'}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.json}
      />
    );

    const code = screen.getByTestId('nv-code-snippet-code');
    expect(code).toHaveTextContent('9007199254740993123456789');
    expect(code).toHaveTextContent('"negative_zero": -0');
    expect(code).toHaveTextContent('"huge": 1e+400');
  });

  it('bounds indentation for deeply nested JSON payloads', () => {
    const nestingDepth = 250;
    renderRoute(
      <SpanPayloadBlock
        value={`${'['.repeat(nestingDepth)}0${']'.repeat(nestingDepth)}`}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.json}
      />
    );

    const renderedJson = screen.getByTestId('nv-code-snippet-code').textContent ?? '';
    const maximumIndentation = Math.max(
      ...renderedJson.split('\n').map((line) => line.length - line.trimStart().length)
    );
    expect(maximumIndentation).toBe(200);
  });

  it('shows a clear error for invalid JSON payloads', () => {
    renderRoute(
      <SpanPayloadBlock
        value="not-json"
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.json}
      />
    );

    expect(screen.getByText('Cannot render as JSON')).toBeInTheDocument();
    expect(screen.getByText(/payload is not valid JSON/i)).toBeInTheDocument();
  });

  it('renders OpenAI request messages as a chat transcript', () => {
    renderRoute(
      <SpanPayloadBlock
        value={JSON.stringify({
          model: 'test-model',
          messages: [
            { role: 'system', content: 'Be concise.' },
            { role: 'user', content: 'What happened?' },
            { role: 'assistant', content: 'The trace completed.' },
          ],
        })}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.chat}
      />
    );

    expect(screen.getByRole('list', { name: 'Chat transcript' })).toBeInTheDocument();
    expect(screen.getByText('System')).toBeInTheDocument();
    expect(screen.getByText('User')).toBeInTheDocument();
    expect(screen.getByText('Assistant')).toBeInTheDocument();
    expect(screen.getByText('What happened?')).toBeInTheDocument();
    expect(screen.getByText('The trace completed.')).toBeInTheDocument();
  });

  it('renders OpenAI response choices as assistant messages', () => {
    renderRoute(
      <SpanPayloadBlock
        value={JSON.stringify({
          choices: [{ message: { role: 'assistant', content: 'Choice response' } }],
        })}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.chat}
      />
    );

    expect(screen.getByText('Assistant')).toBeInTheDocument();
    expect(screen.getByText('Choice response')).toBeInTheDocument();
  });

  it('combines streamed OpenAI response chunks into one assistant message', () => {
    renderRoute(
      <SpanPayloadBlock
        value={JSON.stringify([
          {
            choices: [{ index: 0, delta: { role: 'assistant', content: 'Streamed ' } }],
          },
          { choices: [{ index: 0, delta: { content: 'response' } }] },
        ])}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.chat}
      />
    );

    expect(screen.getByText('Assistant')).toBeInTheDocument();
    expect(screen.getByText('Streamed response')).toBeInTheDocument();
  });

  it('renders OpenAI refusal text when message content is null', () => {
    renderRoute(
      <SpanPayloadBlock
        value={JSON.stringify({
          choices: [
            {
              message: {
                role: 'assistant',
                content: null,
                refusal: 'I cannot help with that request.',
              },
            },
          ],
        })}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.chat}
      />
    );

    expect(screen.getByText('I cannot help with that request.')).toBeInTheDocument();
  });

  it('renders Pydantic-AI message parts in chat mode', () => {
    renderRoute(
      <SpanPayloadBlock
        value={JSON.stringify([
          { role: 'user', parts: [{ type: 'text', content: 'Analyze traces.' }] },
          {
            role: 'assistant',
            parts: [{ type: 'text', content: 'Found a recurring issue.' }],
          },
        ])}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.chat}
      />
    );

    expect(screen.getByText('Analyze traces.')).toBeInTheDocument();
    expect(screen.getByText('Found a recurring issue.')).toBeInTheDocument();
  });

  it('shows a clear error for unsupported chat payloads', () => {
    renderRoute(
      <SpanPayloadBlock
        value={JSON.stringify({ answer: 'No messages here' })}
        emptyMessage="No payload"
        viewMode={SpanPayloadViewMode.chat}
      />
    );

    expect(screen.getByText('Cannot render as chat')).toBeInTheDocument();
    expect(screen.getByText(/No OpenAI-compatible messages were found/i)).toBeInTheDocument();
  });

  it('shows a loader before rendering large payloads', async () => {
    const payload = 'x'.repeat(20_001);

    renderRoute(<SpanPayloadBlock value={payload} emptyMessage="No payload" />);

    expect(screen.getByLabelText('Rendering payload')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByLabelText('Rendering payload')).not.toBeInTheDocument()
    );
    expect(screen.getByTestId('nv-code-snippet-code')).toHaveTextContent(payload);
  });

  it('defers a large payload again when its rendering mode changes', () => {
    vi.useFakeTimers();
    try {
      const payload = JSON.stringify({ content: 'x'.repeat(20_001) });
      const Harness = () => {
        const [viewMode, setViewMode] = useState<SpanPayloadViewMode>(SpanPayloadViewMode.raw);
        return (
          <>
            <button type="button" onClick={() => setViewMode(SpanPayloadViewMode.json)}>
              Render JSON
            </button>
            <SpanPayloadBlock value={payload} emptyMessage="No payload" viewMode={viewMode} />
          </>
        );
      };

      renderRoute(<Harness />);
      expect(screen.getByLabelText('Rendering payload')).toBeInTheDocument();
      act(() => vi.runOnlyPendingTimers());
      expect(screen.queryByLabelText('Rendering payload')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Render JSON' }));

      expect(screen.getByLabelText('Rendering payload')).toBeInTheDocument();
      act(() => vi.runOnlyPendingTimers());
      expect(screen.queryByLabelText('Rendering payload')).not.toBeInTheDocument();
      expect(screen.getByTestId('nv-code-snippet-code')).toHaveTextContent('"content":');
    } finally {
      vi.useRealTimers();
    }
  });

  it('renders the empty state for blank payloads', () => {
    renderRoute(<SpanPayloadBlock value="   " emptyMessage="No payload" />);

    expect(screen.getByText('No payload')).toBeInTheDocument();
  });
});
