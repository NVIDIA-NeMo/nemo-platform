// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { z } from 'zod';

/**
 * Mirrors the entity store's RFC-1035-ish name pattern from
 * `packages/nmp_common/src/nmp/common/entities/constants.py` (`NAME_PATTERN`).
 *
 * Several service DTOs advertise a looser pattern (`^[\w\-.]+$`, max 255), which
 * is what OpenAPI/orval pulls into the generated zod schemas. The stricter
 * pattern is only enforced downstream by the entity store, so validating against
 * the generated schema lets invalid names through to a confusing 422.
 */
export const ENTITY_NAME_REGEXP = /^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}(?<!-)$/;

export const ENTITY_NAME_MIN_LENGTH = 2;
export const ENTITY_NAME_MAX_LENGTH = 63;

export const ENTITY_NAME_HELP =
  'Must start with a lowercase letter and be 2–63 characters. Lowercase letters, numbers, and - _ . @ + only. No consecutive or trailing hyphens.';

const INVALID_BODY = /[^a-z0-9\-@.+_]+/g;
const INVALID_BODY_CHAR = /[^a-z0-9\-@.+_]/g;
const COLLAPSE_DASHES = /-{2,}/g;
const STRIP_LEADING_NON_LETTER = /^[^a-z]+/;
const STRIP_TRAILING_DASH = /-+$/;

/** Rewrite input to satisfy `ENTITY_NAME_REGEXP`, or `undefined` if nothing valid remains. */
export function sanitizeEntityName(input: string): string | undefined {
  const sanitized = input
    .trim()
    .toLowerCase()
    .replace(INVALID_BODY, '-')
    .replace(COLLAPSE_DASHES, '-')
    .replace(STRIP_LEADING_NON_LETTER, '')
    .replace(STRIP_TRAILING_DASH, '')
    .slice(0, ENTITY_NAME_MAX_LENGTH)
    .replace(STRIP_TRAILING_DASH, '');

  return sanitized.length >= ENTITY_NAME_MIN_LENGTH ? sanitized : undefined;
}

/** Rewrite input to satisfy `ENTITY_NAME_REGEXP`, falling back when nothing valid remains. */
export function toValidEntityName(input: string, fallback: string): string {
  return sanitizeEntityName(input) ?? fallback;
}

function listInvalidChars(value: string): string[] {
  const found = value.replace(/[A-Z]/g, '').match(INVALID_BODY_CHAR) ?? [];
  return [...new Set(found)].map((char) => (char === ' ' ? 'spaces' : `"${char}"`));
}

/**
 * First specific rule the value breaks, phrased for a form field, or `undefined`
 * when the value is valid.
 */
export function getEntityNameError(value: string, label = 'Name'): string | undefined {
  if (!value) return `${label} is required.`;
  if (ENTITY_NAME_REGEXP.test(value)) return undefined;

  const suggestion = sanitizeEntityName(value);
  const hint = suggestion && suggestion !== value ? ` Try "${suggestion}".` : '';

  if (value.length > ENTITY_NAME_MAX_LENGTH) {
    return `${label} must be ${ENTITY_NAME_MAX_LENGTH} characters or fewer (currently ${value.length}).${hint}`;
  }
  if (value.length < ENTITY_NAME_MIN_LENGTH) {
    return `${label} must be at least ${ENTITY_NAME_MIN_LENGTH} characters.`;
  }
  if (/[A-Z]/.test(value)) {
    return `${label} must be lowercase.${hint}`;
  }

  const invalidChars = listInvalidChars(value);
  if (invalidChars.length > 0) {
    return `${label} cannot contain ${invalidChars.join(', ')}. Use lowercase letters, numbers, and - _ . @ + only.${hint}`;
  }
  if (!/^[a-z]/.test(value)) {
    return `${label} must start with a lowercase letter.${hint}`;
  }
  if (value.includes('--')) {
    return `${label} cannot contain consecutive hyphens.${hint}`;
  }
  if (value.endsWith('-')) {
    return `${label} cannot end with a hyphen.${hint}`;
  }

  return `${label} is invalid. ${ENTITY_NAME_HELP}${hint}`;
}

/** Zod string schema enforcing `ENTITY_NAME_REGEXP` with per-rule error messages. */
export function entityNameSchema(label = 'Name') {
  return z.string().superRefine((value, ctx) => {
    const message = getEntityNameError(value, label);
    if (message) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message });
    }
  });
}
