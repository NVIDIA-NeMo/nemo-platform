// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { GuardrailCheckMessage } from '@studio/api/guardrail-checks/types';

/** Coerce a message's `content` (string or content-part array) to plain display text. */
export const textFromContent = (content: unknown): string => {
  if (typeof content === 'string') {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) =>
        part && typeof part === 'object' && 'text' in part
          ? String((part as { text?: unknown }).text ?? '')
          : ''
      )
      .join(' ')
      .trim();
  }
  return '';
};

/** First user message text — the check's "Input" (single-turn). */
export const getCheckInputText = (messages: GuardrailCheckMessage[]): string => {
  const userMsg = messages.find((m) => m.role === 'user');
  return userMsg ? textFromContent(userMsg.content) : '';
};

/** First assistant message text — the check's "Output" (single-turn). */
export const getCheckOutputText = (messages: GuardrailCheckMessage[]): string => {
  const assistantMsg = messages.find((m) => m.role === 'assistant');
  return assistantMsg ? textFromContent(assistantMsg.content) : '';
};
