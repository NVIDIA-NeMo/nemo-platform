// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { renderTemplate } from '@studio/components/transform/renderTemplate';

const row = {
  name: 'Ada & Grace',
  tags: ['a', 'b'],
  score: 3,
  reference: { expected: 'a refund', notes: null },
  messages: [{ content: 'hello' }],
};

describe('renderTemplate', () => {
  it('does not HTML-escape a column reference', () => {
    expect(renderTemplate({ who: '{{ name }}' }, row).row).toEqual({ who: 'Ada & Grace' });
  });

  it('keeps surrounding text and combines references', () => {
    expect(renderTemplate({ label: 'by {{ name }} ({{ score }})' }, row).row).toEqual({
      label: 'by Ada & Grace (3)',
    });
  });

  it('reads a dot path into a nested source column', () => {
    expect(renderTemplate({ expected: '{{ reference.expected }}' }, row).row).toEqual({
      expected: 'a refund',
    });
  });

  it('reads an indexed path into an array column', () => {
    expect(renderTemplate({ first: '{{ messages.0.content }}' }, row).row).toEqual({
      first: 'hello',
    });
  });

  it('renders an unresolved path as empty rather than the raw braces', () => {
    expect(renderTemplate({ missing: '{{ reference.absent }}' }, row).row).toEqual({ missing: '' });
  });

  it('renders a nested object or array column as its JSON', () => {
    expect(renderTemplate({ tags: '{{ tags }}' }, row).row).toEqual({ tags: ['a', 'b'] });
  });

  it('preserves the template shape, including arrays', () => {
    expect(renderTemplate({ messages: [{ content: '{{ name }}' }] }, row).row).toEqual({
      messages: [{ content: 'Ada & Grace' }],
    });
  });

  it('drops a Jinja2 filter and flags the result as approximate', () => {
    const { row: output, approximated } = renderTemplate({ who: '{{ name | upper }}' }, row);
    expect(output).toEqual({ who: 'Ada & Grace' });
    expect(approximated).toBe(true);
  });

  it('leaves a constant untouched', () => {
    const { row: output, approximated } = renderTemplate({ role: 'user' }, row);
    expect(output).toEqual({ role: 'user' });
    expect(approximated).toBe(false);
  });
});
