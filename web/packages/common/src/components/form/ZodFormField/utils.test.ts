// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  isRequired,
  getBaseSchema,
  getEnumValues,
  getUnionOptions,
  getFieldName,
  extractDefaults,
} from '@nemo/common/src/components/form/ZodFormField/utils';
import { z } from 'zod';

describe('isRequired', () => {
  it('should return false for ZodOptional schema', () => {
    const schema = z.string().optional();
    expect(isRequired(schema, true)).toBe(false);
    expect(isRequired(schema, false)).toBe(false);
  });

  it('should return false for ZodDefault schema', () => {
    const schema = z.string().default('default value');
    expect(isRequired(schema, true)).toBe(false);
    expect(isRequired(schema, false)).toBe(false);
  });

  it('should return the required parameter for non-optional, non-default schemas', () => {
    const schema = z.string();
    expect(isRequired(schema, true)).toBe(true);
    expect(isRequired(schema, false)).toBe(false);
  });

  it('should handle nested optional schemas', () => {
    const schema = z.object({
      name: z.string().optional(),
      age: z.number(),
    });
    expect(isRequired(schema, true)).toBe(true);
    expect(isRequired(schema, false)).toBe(false);
  });

  it('should handle ZodEnum schemas', () => {
    const schema = z.enum(['option1', 'option2']);
    expect(isRequired(schema, true)).toBe(true);
    expect(isRequired(schema, false)).toBe(false);
  });

  it('should handle ZodUnion schemas', () => {
    const schema = z.union([z.string(), z.number()]);
    expect(isRequired(schema, true)).toBe(true);
    expect(isRequired(schema, false)).toBe(false);
  });
});

describe('getBaseSchema', () => {
  it('should unwrap ZodOptional schema', () => {
    const baseSchema = z.string();
    const optionalSchema = baseSchema.optional();
    const result = getBaseSchema(optionalSchema);
    expect(result).toBe(baseSchema);
  });

  it('should remove default from ZodDefault schema', () => {
    const baseSchema = z.string();
    const defaultSchema = baseSchema.default('default value');
    const result = getBaseSchema(defaultSchema);
    expect(result).toBe(baseSchema);
  });

  it('should return the schema as-is for non-optional, non-default schemas', () => {
    const schema = z.string();
    const result = getBaseSchema(schema);
    expect(result).toBe(schema);
  });

  it('should handle nested unwrapping', () => {
    const baseSchema = z.string();
    const optionalSchema = baseSchema.optional();
    const defaultSchema = optionalSchema.default('default value');
    const result = getBaseSchema(defaultSchema);
    // The result should be the optional schema, not the base schema
    // because default() is applied to optional(), not directly to the base
    expect(result).toBe(baseSchema);
  });

  it('should handle ZodEnum schemas', () => {
    const schema = z.enum(['option1', 'option2']);
    const result = getBaseSchema(schema);
    expect(result).toBe(schema);
  });

  it('should handle ZodUnion schemas', () => {
    const schema = z.union([z.string(), z.number()]);
    const result = getBaseSchema(schema);
    expect(result).toBe(schema);
  });
});

describe('getEnumValues', () => {
  it('should return enum values for ZodEnum', () => {
    const schema = z.enum(['option1', 'option2', 'option3']);
    const result = getEnumValues(schema);
    expect(result).toEqual(['option1', 'option2', 'option3']);
  });

  it('should return literal values for ZodUnion of ZodLiteral strings', () => {
    const schema = z.union([z.literal('value1'), z.literal('value2'), z.literal('value3')]);
    const result = getEnumValues(schema);
    expect(result).toEqual(['value1', 'value2', 'value3']);
  });

  it('should filter out non-string literals in union', () => {
    const schema = z.union([
      z.literal('string1'),
      z.literal(123),
      z.literal('string2'),
      z.literal(true),
    ]);
    const result = getEnumValues(schema);
    expect(result).toEqual(['string1', 'string2']);
  });

  it('should return empty array for non-enum, non-union schemas', () => {
    const stringSchema = z.string();
    const numberSchema = z.number();
    const booleanSchema = z.boolean();
    const objectSchema = z.object({ name: z.string() });

    expect(getEnumValues(stringSchema)).toEqual([]);
    expect(getEnumValues(numberSchema)).toEqual([]);
    expect(getEnumValues(booleanSchema)).toEqual([]);
    expect(getEnumValues(objectSchema)).toEqual([]);
  });

  it('should return empty array for ZodUnion with non-literal options', () => {
    const schema = z.union([z.string(), z.number(), z.boolean()]);
    const result = getEnumValues(schema);
    expect(result).toEqual([]);
  });
});

describe('getUnionOptions', () => {
  it('should return string representations for ZodUnion of ZodLiteral values', () => {
    const schema = z.union([z.literal('string_value'), z.literal(123), z.literal(true)]);
    const result = getUnionOptions(schema);
    expect(result).toEqual(['string_value', '123', 'true']);
  });

  it('should return type names for ZodUnion of primitive types', () => {
    const schema = z.union([z.string(), z.number(), z.boolean()]);
    const result = getUnionOptions(schema);
    expect(result).toEqual(['string', 'number', 'boolean']);
  });

  it('should handle mixed union types', () => {
    const schema = z.union([z.literal('specific_value'), z.string(), z.number(), z.literal(42)]);
    const result = getUnionOptions(schema);
    expect(result).toEqual(['specific_value', 'string', 'number', '42']);
  });

  it('should return empty array for non-union schemas', () => {
    const stringSchema = z.string();
    const numberSchema = z.number();
    const booleanSchema = z.boolean();
    const enumSchema = z.enum(['option1', 'option2']);
    const objectSchema = z.object({ name: z.string() });

    expect(getUnionOptions(stringSchema)).toEqual([]);
    expect(getUnionOptions(numberSchema)).toEqual([]);
    expect(getUnionOptions(booleanSchema)).toEqual([]);
    expect(getUnionOptions(enumSchema)).toEqual([]);
    expect(getUnionOptions(objectSchema)).toEqual([]);
  });

  it('should handle unknown union types', () => {
    const schema = z.union([z.object({ name: z.string() }), z.array(z.string())]);
    const result = getUnionOptions(schema);
    expect(result).toEqual(['unknown', 'unknown']);
  });

  it('should convert non-string literal values to strings', () => {
    const schema = z.union([z.literal(0), z.literal(1.5), z.literal(false), z.literal(null)]);
    const result = getUnionOptions(schema);
    expect(result).toEqual(['0', '1.5', 'false', 'null']);
  });
});

describe('getFieldName', () => {
  it('should convert snake_case to Title Case for simple field names', () => {
    const result = getFieldName('user_name');
    expect(result).toBe('User Name');
  });

  it('should handle single word field names', () => {
    const result = getFieldName('name');
    expect(result).toBe('Name');
  });

  it('should handle field names with multiple underscores', () => {
    const result = getFieldName('first_name_last_name');
    expect(result).toBe('First Name Last Name');
  });

  it('should handle field names with dots and take the last part', () => {
    const result = getFieldName('user.profile.first_name');
    expect(result).toBe('First Name');
  });

  it('should handle field names with multiple dots', () => {
    const result = getFieldName('a.b.c.d.e.field_name');
    expect(result).toBe('Field Name');
  });

  it('should handle field names ending with dots', () => {
    const result = getFieldName('user.profile.');
    expect(result).toBe('');
  });

  it('should handle empty string', () => {
    const result = getFieldName('');
    expect(result).toBe('');
  });

  it('should handle field names with no dots', () => {
    const result = getFieldName('simple_field');
    expect(result).toBe('Simple Field');
  });

  it('should handle field names with underscores and dots', () => {
    const result = getFieldName('user.profile_data.last_updated');
    expect(result).toBe('Last Updated');
  });

  it('should handle single character field names', () => {
    const result = getFieldName('x');
    expect(result).toBe('X');
  });

  it('should handle field names with numbers', () => {
    const result = getFieldName('field_123');
    expect(result).toBe('Field 123');
  });
});

describe('extractDefaults', () => {
  it('should extract defaults from a single object', () => {
    const schema = z.object({
      a: z.string().default('default'),
    });
    const defaults = extractDefaults(schema);
    expect(defaults).toEqual({
      a: 'default',
    });
  });
  it('should extract defaults from a nested object when recursive is true', () => {
    const schema = z.object({
      a: z.object({
        b: z.object({
          c: z.string().default('default'),
        }),
      }),
    });
    const defaults = extractDefaults(schema, true);
    expect(defaults).toEqual({
      a: {
        b: {
          c: 'default',
        },
      },
    });
  });
});
