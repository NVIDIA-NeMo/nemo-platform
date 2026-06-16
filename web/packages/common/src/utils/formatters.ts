// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Returns a formatted string with count and properly pluralized text.
 * @param text - The singular form of the word (e.g., "entry", "file")
 * @param count - The number to display
 * @param plural - Optional custom plural form for irregular words (e.g., "entries", "children").
 *                 If not provided, defaults to appending 's' to the text.
 * @returns Formatted string like "1 entry" or "3 entries"
 * @example
 * getTextWithCount('file', 1)           // "1 file"
 * getTextWithCount('file', 3)           // "3 files"
 * getTextWithCount('entry', 2, 'entries') // "2 entries"
 */
export const getTextWithCount = (text: string, count: number, plural?: string) => {
  const pluralForm = plural ?? `${text}s`;
  return `${count} ${count !== 1 ? pluralForm : text}`;
};

/**
 * Truncates a long string of text to the length specified by `maxCharacters` by replacing a
 * section of the text with an ellipsis.
 *
 * @param text the text to truncate
 * @param maxCharacters the maximum number of characters (including 3 chars for ...)
 * @param mode specifies where to put the ellipses
 */
export const truncateText = (
  text: string,
  maxCharacters: number,
  mode: 'start' | 'middle' | 'end' = 'end'
) => {
  if (text.length <= maxCharacters) return text; // No truncation needed

  const ellipsis = '...';
  const charsToShow = maxCharacters - ellipsis.length;

  if (charsToShow <= 0) return ellipsis; // Edge case: maxCharacters is too small to include text

  switch (mode) {
    case 'start': {
      return `${ellipsis}${text.slice(-charsToShow)}`;
    }
    case 'middle': {
      const half = Math.floor(charsToShow / 2);
      return `${text.slice(0, half)}${ellipsis}${text.slice(-half)}`;
    }
    case 'end':
    default: {
      return `${text.slice(0, charsToShow)}${ellipsis}`;
    }
  }
};

/**
 * Converts an unknown value to a string. Useful when displaying unknown values in a UI.
 * @param value - The value to convert.
 * @returns A string representation of the value.
 */
export const unknownToString = (value: unknown) => {
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint')
    return value.toString();
  if (value instanceof Date) return value.toISOString();
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      // Fallback for circular structures or `toJSON` failures
      return String(value);
    }
  }
  return String(value);
};

import type { FinetuningType } from '@nemo/sdk/generated/platform/schema';

/** Maps FinetuningType enum values to their correct display labels. */
const FINETUNING_TYPE_LABELS: Record<FinetuningType, string> = {
  lora: 'LoRA',
  lora_merged: 'LoRA Merged',
  all_weights: 'All Weights',
  last_layer: 'Last Layer',
  top_layers: 'Top Layers',
  gradual_unfreezing: 'Gradual Unfreezing',
  bias_only: 'Bias Only',
  attention_only: 'Attention Only',
  qlora: 'QLoRA',
  adalora: 'AdaLoRA',
  dora: 'DoRA',
  lora_plus: 'LoRA+',
  prompt_tuning: 'Prompt Tuning',
  prefix_tuning: 'Prefix Tuning',
  p_tuning: 'P-Tuning',
  p_tuning_v2: 'P-Tuning v2',
  soft_prompt: 'Soft Prompt',
  ppo: 'PPO',
  dpo: 'DPO',
  cdpo: 'cDPO',
  ipo: 'IPO',
  orpo: 'ORPO',
  kto: 'KTO',
  rrhf: 'RRHF',
  grpo: 'GRPO',
};

/** Format a FinetuningType enum value for display. Falls back to the raw value for unknown types. */
export const formatFinetuningType = (type: FinetuningType): string =>
  FINETUNING_TYPE_LABELS[type] || type;

export const kebabCaseToTitleCase = (str: string) => {
  return str.replace(/-/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
};

export const snakeCaseToTitleCase = (str: string) => {
  return str.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
};

/**
 * Converts a number to scientific notation string if it is very small or large.
 */
export const toScientificNotation = (value: number) => {
  if ((Math.abs(value) < 1e-6 && value !== 0) || Math.abs(value) >= 1e15) {
    return value.toExponential();
  }
  return value.toString();
};

const COLORS = ['#76b900', '#9525c6', '#ef9100', '#d2308e', '#1dbba4'];
/**
 * Returns a color array of length N using the secondary color palette from KUI. Repeats past 5 colors.
 * @param length - The length of the array.
 */
export const getColorsFromLength = (length: number) => {
  return Array.from({ length }, (_, index) => COLORS[index % COLORS.length]);
};
