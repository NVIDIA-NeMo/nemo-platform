// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { extractUserMessage } from '@studio/util/llm';

describe('extractUserMessage', () => {
  it('should return user message content when messages contain a user role', () => {
    const row = {
      messages: [
        { role: 'system' as const, content: 'You are a helpful assistant.' },
        { role: 'user' as const, content: 'Hello there!' },
      ],
    };
    expect(extractUserMessage({ row })).toBe('Hello there!');
  });

  it('should return empty string when messages exist but no user role', () => {
    const row = {
      messages: [
        { role: 'system' as const, content: 'System prompt' },
        { role: 'assistant' as const, content: 'Hi!' },
      ],
    };
    expect(extractUserMessage({ row })).toBe('');
  });

  it('should use Handlebars template when no messages are present', () => {
    const row = { name: 'Alice', question: 'What is AI?' };
    const template = 'Hello {{name}}, your question: {{question}}';
    expect(extractUserMessage({ row, template })).toBe('Hello Alice, your question: What is AI?');
  });

  it('should return empty string when template compilation fails', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const row = { name: 'Alice' };
    // Handlebars throws on malformed block helpers
    const template = '{{#if}}missing closing';
    expect(extractUserMessage({ row, template })).toBe('');
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it('should return empty string when no messages and no template', () => {
    const row = { someField: 'value' };
    expect(extractUserMessage({ row })).toBe('');
  });

  it('should prefer messages over template when both exist', () => {
    const row = {
      messages: [{ role: 'user' as const, content: 'From messages' }],
      name: 'Alice',
    };
    const template = 'Hello {{name}}';
    expect(extractUserMessage({ row, template })).toBe('From messages');
  });
});
