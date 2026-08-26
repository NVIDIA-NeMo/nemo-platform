// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  CUSTOM_FORMAT_ID,
  findOutputFormat,
  type OutputFormat,
} from '@studio/components/transform/formats';
import {
  autoMapFields,
  buildTemplate,
  columnReference,
  missingRequiredPaths,
  resolveGeneratedIdColumn,
  setAtPath,
  templateReferences,
  usesGeneratedIdColumn,
} from '@studio/components/transform/template';

const agentEvalTask = findOutputFormat('agent-eval-task') as OutputFormat;
const chatMessages = findOutputFormat('chat-messages') as OutputFormat;
const custom = findOutputFormat(CUSTOM_FORMAT_ID) as OutputFormat;

describe('setAtPath', () => {
  it('writes a top-level key', () => {
    expect(setAtPath({}, 'id', '{{ task_id }}')).toEqual({ id: '{{ task_id }}' });
  });

  it('creates nested objects for dot paths', () => {
    expect(setAtPath({}, 'inputs.instruction', '{{ q }}')).toEqual({
      inputs: { instruction: '{{ q }}' },
    });
  });

  it('creates arrays for numeric segments', () => {
    const target = {};
    setAtPath(target, 'messages.0.content', '{{ q }}');
    setAtPath(target, 'messages.1.content', '{{ a }}');
    expect(target).toEqual({ messages: [{ content: '{{ q }}' }, { content: '{{ a }}' }] });
  });

  it('merges into an existing container rather than replacing it', () => {
    const target = { inputs: { instruction: '{{ q }}' } };
    setAtPath(target, 'inputs.context', '{{ c }}');
    expect(target).toEqual({ inputs: { instruction: '{{ q }}', context: '{{ c }}' } });
  });

  it('replaces a container whose shape does not match the next segment', () => {
    const target = { messages: { content: 'wrong shape' } };
    setAtPath(target, 'messages.0.content', '{{ q }}');
    expect(target).toEqual({ messages: [{ content: '{{ q }}' }] });
  });

  it('drops a path that traverses the prototype chain', () => {
    const target: Record<string, unknown> = {};
    setAtPath(target, '__proto__.polluted', 'yes');
    setAtPath(target, 'constructor', 'yes');
    expect(target).toEqual({});
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it('ignores an empty path', () => {
    expect(setAtPath({ a: 1 }, '', 'x')).toEqual({ a: 1 });
  });
});

describe('buildTemplate', () => {
  it('nests preset fields at their declared paths', () => {
    const template = buildTemplate(
      agentEvalTask,
      {
        id: '{{ task_id }}',
        intent: '{{ category }}',
        'inputs.instruction': '{{ user_request }}',
        'reference.expected': '{{ ideal_response }}',
      },
      []
    );
    expect(template).toEqual({
      id: '{{ task_id }}',
      intent: '{{ category }}',
      inputs: { instruction: '{{ user_request }}' },
      reference: { expected: '{{ ideal_response }}' },
    });
  });

  it('omits blank mappings instead of emitting empty strings', () => {
    const template = buildTemplate(agentEvalTask, { id: '{{ task_id }}', intent: '  ' }, []);
    expect(template).toEqual({ id: '{{ task_id }}' });
  });

  it('emits format constants alongside mapped fields', () => {
    const template = buildTemplate(
      chatMessages,
      { 'messages.0.content': '{{ q }}', 'messages.1.content': '{{ a }}' },
      []
    );
    expect(template).toEqual({
      messages: [
        { content: '{{ q }}', role: 'user' },
        { content: '{{ a }}', role: 'assistant' },
      ],
    });
  });

  it('keeps constants even when the paired field is unmapped', () => {
    const template = buildTemplate(chatMessages, {}, []);
    expect(template).toEqual({ messages: [{ role: 'user' }, { role: 'assistant' }] });
  });

  it('builds custom rows and skips ones with no key', () => {
    const template = buildTemplate(custom, {}, [
      { key: 'instruction', value: '{{ prompt }}' },
      { key: '', value: '{{ ignored }}' },
      { key: 'meta.source', value: 'data-designer' },
    ]);
    expect(template).toEqual({
      instruction: '{{ prompt }}',
      meta: { source: 'data-designer' },
    });
  });
});

describe('autoMapFields', () => {
  it('prefers an exact hint match over a substring match', () => {
    const mappings = autoMapFields(agentEvalTask, ['row_id', 'id', 'intent']);
    expect(mappings.id).toBe('{{ id }}');
  });

  it('falls back to a whole-word match inside a compound name', () => {
    const mappings = autoMapFields(agentEvalTask, ['task_id', 'user_request']);
    expect(mappings['inputs.instruction']).toBe('{{ user_request }}');
  });

  it('matches camelCase names too', () => {
    const mappings = autoMapFields(agentEvalTask, ['taskId', 'userRequest']);
    expect(mappings.id).toBe('{{ taskId }}');
    expect(mappings['inputs.instruction']).toBe('{{ userRequest }}');
  });

  it('does not let a short hint swallow an unrelated column', () => {
    // `ideal_response` contains the substring "id" but has no `id` word.
    const mappings = autoMapFields(agentEvalTask, ['category', 'ideal_response']);
    expect(mappings.id).toBeUndefined();
    expect(mappings['reference.expected']).toBe('{{ ideal_response }}');
  });

  it('never assigns the same column to two fields', () => {
    const mappings = autoMapFields(chatMessages, ['response']);
    const used = Object.values(mappings);
    expect(new Set(used).size).toBe(used.length);
  });

  it('leaves a field unmapped when nothing matches', () => {
    const mappings = autoMapFields(agentEvalTask, ['alpha', 'beta']);
    expect(mappings['inputs.instruction']).toBeUndefined();
  });
});

describe('resolveGeneratedIdColumn', () => {
  it('uses the plain name when the source has no such column', () => {
    expect(resolveGeneratedIdColumn(['task_id', 'prompt'])).toBe('row_id');
  });

  it('suffixes past a collision, since a declared column cannot shadow a seed column', () => {
    expect(resolveGeneratedIdColumn(['row_id'])).toBe('row_id_2');
    expect(resolveGeneratedIdColumn(['row_id', 'row_id_2'])).toBe('row_id_3');
  });
});

describe('autoMapFields with a generated id', () => {
  it('falls back to the generated column for an identity field with no match', () => {
    const mappings = autoMapFields(agentEvalTask, ['prompt', 'answer'], 'row_id');
    expect(mappings.id).toBe('{{ row_id }}');
  });

  it('prefers a real source column over generating one', () => {
    const mappings = autoMapFields(agentEvalTask, ['task_id', 'prompt'], 'row_id');
    expect(mappings.id).toBe('{{ task_id }}');
  });

  it('does not generate for non-identity fields', () => {
    const mappings = autoMapFields(agentEvalTask, ['task_id'], 'row_id');
    expect(mappings['inputs.instruction']).toBeUndefined();
  });
});

describe('templateReferences', () => {
  it('collects root names through nesting, arrays, and filters', () => {
    const refs = templateReferences({
      id: '{{ row_id }}',
      inputs: { instruction: '{{ prompt | trim }}' },
      messages: [{ content: '{{ a.b.c }}' }],
      literal: 'no references here',
    });
    expect([...refs].sort()).toEqual(['a', 'prompt', 'row_id']);
  });
});

describe('usesGeneratedIdColumn', () => {
  it('is true when the template references the generated column', () => {
    expect(usesGeneratedIdColumn({ id: '{{ row_id }}' }, 'row_id', ['prompt'])).toBe(true);
  });

  it('is false once the reference is gone', () => {
    expect(usesGeneratedIdColumn({ id: '{{ prompt }}' }, 'row_id', ['prompt'])).toBe(false);
  });

  it('is false when the name is a real source column, which needs no sampler', () => {
    expect(usesGeneratedIdColumn({ id: '{{ row_id }}' }, 'row_id', ['row_id'])).toBe(false);
  });
});

describe('missingRequiredPaths', () => {
  it('lists only required fields with no template', () => {
    expect(missingRequiredPaths(agentEvalTask, { id: '{{ task_id }}' })).toEqual([
      'intent',
      'inputs.instruction',
    ]);
  });

  it('is empty once every required field is mapped', () => {
    expect(
      missingRequiredPaths(agentEvalTask, {
        id: '{{ a }}',
        intent: '{{ b }}',
        'inputs.instruction': '{{ c }}',
      })
    ).toEqual([]);
  });
});

describe('columnReference', () => {
  it('wraps a column in Jinja2 delimiters', () => {
    expect(columnReference('user_request')).toBe('{{ user_request }}');
  });
});
