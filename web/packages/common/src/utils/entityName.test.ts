// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ENTITY_NAME_REGEXP,
  entityNameSchema,
  getEntityNameError,
  sanitizeEntityName,
  toValidEntityName,
} from '@nemo/common/src/utils/entityName';

describe('getEntityNameError', () => {
  it.each(['sparl', 'a1', 'my-provider', 'llama-3.2-3b-instruct@v1.0.0+A100'.toLowerCase(), 'a_b'])(
    'accepts %s',
    (value) => {
      expect(getEntityNameError(value)).toBeUndefined();
    }
  );

  it('reports a missing value', () => {
    expect(getEntityNameError('')).toBe('Name is required.');
  });

  it('reports uppercase with a lowercased suggestion', () => {
    expect(getEntityNameError('Sparl')).toBe('Name must be lowercase. Try "sparl".');
  });

  it('lists the disallowed characters', () => {
    expect(getEntityNameError('invalid name!')).toContain('cannot contain spaces, "!"');
  });

  it('reports a leading non-letter', () => {
    expect(getEntityNameError('1provider')).toBe(
      'Name must start with a lowercase letter. Try "provider".'
    );
  });

  it('reports consecutive hyphens', () => {
    expect(getEntityNameError('my--provider')).toBe(
      'Name cannot contain consecutive hyphens. Try "my-provider".'
    );
  });

  it('reports a trailing hyphen', () => {
    expect(getEntityNameError('myprovider-')).toBe(
      'Name cannot end with a hyphen. Try "myprovider".'
    );
  });

  it('reports too-short values without a bogus suggestion', () => {
    expect(getEntityNameError('a')).toBe('Name must be at least 2 characters.');
  });

  it('reports too-long values with the current length', () => {
    expect(getEntityNameError('a'.repeat(64))).toContain(
      'Name must be 63 characters or fewer (currently 64).'
    );
  });

  it('uses the supplied label', () => {
    expect(getEntityNameError('', 'Provider name')).toBe('Provider name is required.');
  });
});

describe('sanitizeEntityName', () => {
  it.each([
    'Qwen3.6-35B-A3B-MTP-GGUF',
    'mistralai/Mistral-7B-Instruct-v0.3',
    'hello world',
    '   leading-trailing   ',
    '123-starts-with-digit',
    'has--double--dashes',
    'ends-with-dash-',
    'x'.repeat(200),
  ])('produces a valid name for %s', (input) => {
    const result = sanitizeEntityName(input);
    expect(result).toBeDefined();
    expect(ENTITY_NAME_REGEXP.test(result as string)).toBe(true);
  });

  it('returns undefined when nothing valid remains', () => {
    expect(sanitizeEntityName('!!!')).toBeUndefined();
    expect(sanitizeEntityName('')).toBeUndefined();
  });
});

describe('toValidEntityName', () => {
  it('falls back when nothing valid remains', () => {
    expect(toValidEntityName('!!!', 'provider')).toBe('provider');
  });
});

describe('entityNameSchema', () => {
  it('surfaces the rule-specific message', () => {
    const result = entityNameSchema('Provider name').safeParse('Sparl');
    expect(result.success).toBe(false);
    expect(result.success === false && result.error.issues[0].message).toBe(
      'Provider name must be lowercase. Try "sparl".'
    );
  });

  it('passes valid names through', () => {
    expect(entityNameSchema().safeParse('sparl')).toMatchObject({ success: true, data: 'sparl' });
  });
});
