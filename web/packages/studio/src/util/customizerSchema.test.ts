// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  CUSTOMIZER_SCHEMA_LABELS,
  detectCustomizerSchema,
  expectedSchemaCopy,
  inferRowSchema,
  validateRowCompleteness,
} from '@studio/util/customizerSchema';

describe('detectCustomizerSchema', () => {
  describe('SFT', () => {
    it('detects messages (chat) when first message has a role', () => {
      const row = {
        messages: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'hello' },
        ],
      };
      expect(detectCustomizerSchema(row, 'sft')).toEqual({
        variant: 'sft-chat',
        label: CUSTOMIZER_SCHEMA_LABELS['sft-chat'],
      });
    });

    it('detects prompt + completion', () => {
      const row = { prompt: 'capital of France?', completion: 'Paris' };
      expect(detectCustomizerSchema(row, 'sft')).toEqual({
        variant: 'sft-prompt-completion',
        label: CUSTOMIZER_SCHEMA_LABELS['sft-prompt-completion'],
      });
    });

    it('rejects DPO-shaped rows under SFT', () => {
      const row = { prompt: 'p', chosen: 'c', rejected: 'r' };
      // BinaryPreference is a DPO shape; SFT rules accept prompt+completion only.
      // The SFT detector only sees prompt and falls through.
      expect(detectCustomizerSchema(row, 'sft')).toBeNull();
    });

    it('rejects rows that match no SFT shape', () => {
      expect(detectCustomizerSchema({ foo: 'bar' }, 'sft')).toBeNull();
    });

    it('rejects empty messages array (no first message to verify role)', () => {
      expect(detectCustomizerSchema({ messages: [] }, 'sft')).toBeNull();
    });

    it('rejects messages array whose first item has no role field', () => {
      expect(detectCustomizerSchema({ messages: [{ content: 'hi' }] }, 'sft')).toBeNull();
    });

    it('returns null for null input', () => {
      expect(detectCustomizerSchema(null, 'sft')).toBeNull();
    });
  });

  describe('DPO', () => {
    it('detects native PreferenceDataset (context + completions)', () => {
      const row = {
        context: [{ role: 'user', content: 'hi' }],
        completions: [{ rank: 0, completion: [{ role: 'assistant', content: 'hello' }] }],
      };
      expect(detectCustomizerSchema(row, 'dpo')).toEqual({
        variant: 'dpo-preference',
        label: CUSTOMIZER_SCHEMA_LABELS['dpo-preference'],
      });
    });

    it('detects HelpSteer3 by overall_preference field', () => {
      const row = {
        context: 'explain quantum',
        response1: 'a',
        response2: 'b',
        overall_preference: -2,
      };
      expect(detectCustomizerSchema(row, 'dpo')).toEqual({
        variant: 'dpo-helpsteer3',
        label: CUSTOMIZER_SCHEMA_LABELS['dpo-helpsteer3'],
      });
    });

    it('detects Tulu3 when chosen is a list of messages', () => {
      const row = {
        chosen: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'hello' },
        ],
        rejected: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'go away' },
        ],
      };
      expect(detectCustomizerSchema(row, 'dpo')).toEqual({
        variant: 'dpo-tulu3',
        label: CUSTOMIZER_SCHEMA_LABELS['dpo-tulu3'],
      });
    });

    it('falls back to BinaryPreference when chosen/rejected are strings', () => {
      const row = { prompt: 'capital?', chosen: 'Paris', rejected: 'London' };
      expect(detectCustomizerSchema(row, 'dpo')).toEqual({
        variant: 'dpo-binary-preference',
        label: CUSTOMIZER_SCHEMA_LABELS['dpo-binary-preference'],
      });
    });

    it('rejects SFT prompt+completion under DPO', () => {
      expect(detectCustomizerSchema({ prompt: 'a', completion: 'b' }, 'dpo')).toBeNull();
    });

    it('rejects rows that match no DPO shape', () => {
      expect(detectCustomizerSchema({ foo: 'bar' }, 'dpo')).toBeNull();
    });
  });
});

describe('validateRowCompleteness', () => {
  describe('sft-prompt-completion', () => {
    it('passes when prompt and completion are non-empty strings', () => {
      expect(
        validateRowCompleteness({ prompt: 'p', completion: 'c' }, 'sft-prompt-completion')
      ).toBeNull();
    });

    it('flags empty prompt', () => {
      expect(
        validateRowCompleteness({ prompt: '', completion: 'c' }, 'sft-prompt-completion')
      ).toMatch(/prompt is missing or empty/);
    });

    it('flags empty completion', () => {
      expect(
        validateRowCompleteness({ prompt: 'p', completion: '' }, 'sft-prompt-completion')
      ).toMatch(/completion is missing or empty/);
    });

    it('flags missing completion key', () => {
      expect(validateRowCompleteness({ prompt: 'p' }, 'sft-prompt-completion')).toMatch(
        /completion is missing or empty/
      );
    });
  });

  describe('sft-chat', () => {
    it('passes when every message has role + content', () => {
      const row = {
        messages: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'hello' },
        ],
      };
      expect(validateRowCompleteness(row, 'sft-chat')).toBeNull();
    });

    it('passes when content is missing but tool_calls is non-empty', () => {
      const row = {
        messages: [
          { role: 'assistant', tool_calls: [{ type: 'function', function: { name: 'x' } }] },
        ],
      };
      expect(validateRowCompleteness(row, 'sft-chat')).toBeNull();
    });

    it('flags an empty messages array', () => {
      expect(validateRowCompleteness({ messages: [] }, 'sft-chat')).toMatch(
        /messages must be a non-empty array/
      );
    });

    it('flags a message missing role', () => {
      expect(validateRowCompleteness({ messages: [{ content: 'hi' }] }, 'sft-chat')).toMatch(
        /messages\[0\]\.role is missing or empty/
      );
    });

    it('flags a message missing all of content/thinking/tool_calls', () => {
      expect(validateRowCompleteness({ messages: [{ role: 'user' }] }, 'sft-chat')).toMatch(
        /must have non-empty content, thinking, or tool_calls/
      );
    });

    it('flags a message that has BOTH content and thinking (backend rejects)', () => {
      // services/customizer/.../schemas.py:292 — SFTChatMessage validator
      // rejects messages with both fields populated. Studio must mirror that
      // so users see the failure pre-submit instead of at training time.
      const row = {
        messages: [{ role: 'assistant', content: 'answer', thinking: 'reasoning' }],
      };
      expect(validateRowCompleteness(row, 'sft-chat')).toMatch(
        /cannot have both content and thinking/
      );
    });
  });

  describe('dpo-binary-preference', () => {
    it('passes for non-empty prompt/chosen/rejected strings', () => {
      expect(
        validateRowCompleteness(
          { prompt: 'p', chosen: 'c', rejected: 'r' },
          'dpo-binary-preference'
        )
      ).toBeNull();
    });

    it('passes when prompt is a non-empty list of messages', () => {
      expect(
        validateRowCompleteness(
          {
            prompt: [{ role: 'user', content: 'hi' }],
            chosen: 'c',
            rejected: 'r',
          },
          'dpo-binary-preference'
        )
      ).toBeNull();
    });

    it('flags empty rejected', () => {
      expect(
        validateRowCompleteness({ prompt: 'p', chosen: 'c', rejected: '' }, 'dpo-binary-preference')
      ).toMatch(/rejected is missing or empty/);
    });

    it('flags non-string non-array prompt', () => {
      expect(
        validateRowCompleteness({ prompt: 42, chosen: 'c', rejected: 'r' }, 'dpo-binary-preference')
      ).toMatch(/prompt must be a non-empty string or list of messages/);
    });
  });

  describe('dpo-tulu3', () => {
    it('passes for non-empty chosen/rejected message lists', () => {
      const row = {
        chosen: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'hello' },
        ],
        rejected: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'go away' },
        ],
      };
      expect(validateRowCompleteness(row, 'dpo-tulu3')).toBeNull();
    });

    it('flags empty chosen list', () => {
      const row = {
        chosen: [],
        rejected: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'go away' },
        ],
      };
      expect(validateRowCompleteness(row, 'dpo-tulu3')).toMatch(
        /chosen: messages must be a non-empty array/
      );
    });
  });

  describe('dpo-preference', () => {
    it('flags missing context', () => {
      expect(validateRowCompleteness({ completions: [{ rank: 0 }] }, 'dpo-preference')).toMatch(
        /context: messages must be a non-empty array/
      );
    });

    it('flags empty completions', () => {
      const row = {
        context: [{ role: 'user', content: 'hi' }],
        completions: [],
      };
      expect(validateRowCompleteness(row, 'dpo-preference')).toMatch(
        /completions must be a non-empty array/
      );
    });
  });

  describe('dpo-helpsteer3', () => {
    it('passes for valid HelpSteer3 row', () => {
      const row = {
        context: 'explain quantum',
        response1: 'a',
        response2: 'b',
        overall_preference: 0,
      };
      expect(validateRowCompleteness(row, 'dpo-helpsteer3')).toBeNull();
    });

    it('flags non-numeric overall_preference', () => {
      const row = {
        context: 'explain quantum',
        response1: 'a',
        response2: 'b',
        overall_preference: 'high',
      };
      expect(validateRowCompleteness(row, 'dpo-helpsteer3')).toMatch(
        /overall_preference must be a number/
      );
    });

    it('flags empty response1', () => {
      const row = {
        context: 'explain quantum',
        response1: '',
        response2: 'b',
        overall_preference: 0,
      };
      expect(validateRowCompleteness(row, 'dpo-helpsteer3')).toMatch(
        /response1 is missing or empty/
      );
    });
  });
});

describe('CUSTOMIZER_SCHEMA_LABELS', () => {
  it('pins the user-facing label for every variant', () => {
    // Update intentionally: canonical names were chosen for the panel checklist
    // ("Schema: Chat Completion" rather than "Schema: messages (chat)"). Bumping
    // these values is a UX decision — fail this test loudly to force a review.
    expect(CUSTOMIZER_SCHEMA_LABELS).toEqual({
      'sft-chat': 'Chat Completion',
      'sft-prompt-completion': 'Completion',
      'dpo-preference': 'Preference',
      'dpo-helpsteer3': 'HelpSteer3',
      'dpo-tulu3': 'Tulu3',
      'dpo-binary-preference': 'Binary Preference',
    });
  });
});

describe('expectedSchemaCopy', () => {
  it('returns DPO copy for dpo training', () => {
    expect(expectedSchemaCopy('dpo')).toMatch(/chosen and rejected/);
  });

  it('returns SFT copy for sft training', () => {
    expect(expectedSchemaCopy('sft')).toMatch(/messages.*prompt and completion/);
  });
});

describe('inferRowSchema', () => {
  it('returns empty string for null input', () => {
    expect(inferRowSchema(null)).toBe('');
  });

  it('renders flat primitive types', () => {
    expect(inferRowSchema({ prompt: 'hi', score: 1, ok: true })).toBe(
      ['{', '  prompt: string,', '  score: number,', '  ok: boolean,', '}'].join('\n')
    );
  });

  it('renders null values as the literal `null`', () => {
    expect(inferRowSchema({ trace: null })).toBe(['{', '  trace: null,', '}'].join('\n'));
  });

  it('expands nested objects so the structure is fully visible', () => {
    expect(inferRowSchema({ answers: { value: 'x', score: 1 } })).toBe(
      ['{', '  answers: {', '    value: string,', '    score: number,', '  },', '}'].join('\n')
    );
  });

  it('expands arrays of objects (e.g. messages) into multi-line form', () => {
    const row = {
      messages: [
        { role: 'user', content: 'hi' },
        { role: 'assistant', content: 'hello' },
      ],
    };
    expect(inferRowSchema(row)).toBe(
      [
        '{',
        '  messages: [',
        '    {',
        '      role: string,',
        '      content: string,',
        '    },',
        '  ],',
        '}',
      ].join('\n')
    );
  });

  it('uses single-line form for arrays of primitives', () => {
    expect(inferRowSchema({ tags: ['a', 'b', 'c'] })).toBe(
      ['{', '  tags: [string],', '}'].join('\n')
    );
  });

  it('renders empty containers as `{}` and `[]` rather than recursing', () => {
    expect(inferRowSchema({ extras: {}, neg_doc: [] })).toBe(
      ['{', '  extras: {},', '  neg_doc: [],', '}'].join('\n')
    );
  });

  it('uses the FIRST element to represent heterogeneous arrays', () => {
    // Documented limitation: schema-mismatch row catches the broader case.
    expect(inferRowSchema({ rows: [{ a: 1 }, { b: 'x' }] as Array<Record<string, unknown>> })).toBe(
      ['{', '  rows: [', '    {', '      a: number,', '    },', '  ],', '}'].join('\n')
    );
  });

  it('caps recursion depth so degenerate inputs do not loop', () => {
    // Depth cap is 8; build a 12-deep nested object and assert the deepest
    // layers collapse to `unknown` rather than running away.
    let nested: Record<string, unknown> = { v: 'leaf' };
    for (let i = 0; i < 12; i++) {
      nested = { wrap: nested };
    }
    expect(inferRowSchema(nested)).toContain('unknown');
  });
});
