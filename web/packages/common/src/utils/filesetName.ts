// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Mirrors the entity store's RFC-1035-ish name pattern from
 * `packages/nmp_common/src/nmp/common/entities/constants.py` (`NAME_PATTERN`):
 *
 *   ^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}(?<!-)$
 *
 *   - 2-63 chars total
 *   - First char must be a lowercase letter
 *   - Body chars: lowercase letters, digits, `-`, `@`, `.`, `+`, `_`
 *   - No consecutive `--`
 *   - No trailing `-`
 *
 * The Files service's `CreateFilesetRequest` DTO advertises a looser pattern
 * (`^[\w\-.]+$`, max 255), which is what OpenAPI/orval pulls into zod. The
 * stricter pattern is only enforced downstream by the entity store, so the
 * generated SDK and a naive sanitizer let invalid names through to a confusing
 * 422 at write time.
 */

/** Source-of-truth regex for fileset names. */
export const FILESET_NAME_REGEXP = /^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}(?<!-)$/;

/** Max length (first char + 62) per the entity store pattern. */
export const FILESET_NAME_MAX_LENGTH = 63;

/** Fallback when the input sanitizes down to nothing valid. */
const FALLBACK = 'fileset';

const INVALID_BODY = /[^a-z0-9\-@.+_]+/g;
const COLLAPSE_DASHES = /-{2,}/g;
const STRIP_LEADING_NON_LETTER = /^[^a-z]+/;
const STRIP_TRAILING_DASH = /-+$/;

/**
 * Rewrite any input into a value that satisfies `FILESET_NAME_REGEXP`.
 *
 * Strategy: lowercase, replace disallowed body chars with `-`, collapse `--`,
 * strip leading non-letter chars (first char must be `[a-z]`), strip trailing
 * `-`, truncate to 63 chars, then strip any newly-exposed trailing `-`.
 * Falls back to `"fileset"` when nothing valid remains.
 */
export function toValidFilesetName(input: string): string {
  let s = input
    .trim()
    .toLowerCase()
    .replace(INVALID_BODY, '-')
    .replace(COLLAPSE_DASHES, '-')
    .replace(STRIP_LEADING_NON_LETTER, '')
    .replace(STRIP_TRAILING_DASH, '')
    .slice(0, FILESET_NAME_MAX_LENGTH)
    .replace(STRIP_TRAILING_DASH, '');

  // Min length is 2 (one leading letter + at least one body char).
  if (s.length < 2) s = FALLBACK;
  return s;
}
