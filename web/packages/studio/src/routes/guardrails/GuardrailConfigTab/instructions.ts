// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Instruction } from '@nemo/sdk/generated/platform/schema';

/**
 * The instruction type the core guardrails engine reads. Only the first
 * `general` instruction is rendered into the guardrail prompts; other types are
 * ignored by the core engine (though some third-party rails read them all).
 */
export const GENERAL_INSTRUCTION_TYPE = 'general';

/** Content of the first `general` instruction, or '' when there isn't one. */
export const getGeneralInstruction = (instructions: Instruction[] | undefined): string =>
  instructions?.find((instruction) => instruction.type === GENERAL_INSTRUCTION_TYPE)?.content ?? '';

/**
 * Return a new instructions array with the first `general` instruction's content
 * set to `content`, preserving every other instruction and the original order.
 *
 * - No general instruction yet + non-empty `content` → one is appended.
 * - `content` is blank → the first general instruction (if any) is removed, so we
 *   never persist an empty one. Non-general instructions are left untouched.
 */
export const setGeneralInstruction = (
  instructions: Instruction[] | undefined,
  content: string
): Instruction[] => {
  const list = instructions ?? [];
  const index = list.findIndex((instruction) => instruction.type === GENERAL_INSTRUCTION_TYPE);

  if (content.trim() === '') {
    return index === -1 ? list : list.filter((_, i) => i !== index);
  }
  if (index === -1) {
    return [...list, { type: GENERAL_INSTRUCTION_TYPE, content }];
  }
  return list.map((instruction, i) => (i === index ? { ...instruction, content } : instruction));
};
