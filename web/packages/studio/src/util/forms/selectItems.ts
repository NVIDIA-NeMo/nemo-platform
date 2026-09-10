// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Select options derived from a generated enum, rather than a hand-written table.
 *
 * The generated enums come from the OpenAPI spec, so deriving options means a value the
 * backend adds shows up on its own. A hand-maintained label table drifts silently instead:
 * the new value is simply absent from the dropdown, and nothing fails.
 *
 * Values are shown as they are. `adamw_8bit` and `bf16` are what the API documents and what
 * the tuning references call them, so re-spelling them as "AdamW 8-bit" adds a translation
 * step without adding meaning. Pass `overrides` only where the raw value would actively
 * mislead — a `"true"`/`"false"` enum reads as a bug in a dropdown.
 */
export const selectItems = <T extends Record<string, string>>(
  values: T,
  overrides: Partial<Record<T[keyof T], string>> = {}
): { value: T[keyof T]; children: string }[] =>
  Object.values(values).map((value) => {
    const key = value as T[keyof T];
    return { value: key, children: overrides[key] ?? value };
  });
