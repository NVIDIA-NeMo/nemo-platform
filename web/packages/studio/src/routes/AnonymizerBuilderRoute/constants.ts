// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const SOURCE_TYPE_URL = 'url';
export const SOURCE_TYPE_DATASET = 'dataset';

export type SourceType = typeof SOURCE_TYPE_URL | typeof SOURCE_TYPE_DATASET;

export const SOURCE_TYPE_OPTIONS: { label: string; value: SourceType }[] = [
  { label: 'Dataset', value: SOURCE_TYPE_DATASET },
  { label: 'URL', value: SOURCE_TYPE_URL },
];

export const STRATEGY_SUBSTITUTE = 'substitute';
export const STRATEGY_REDACT = 'redact';
export const STRATEGY_ANNOTATE = 'annotate';
export const STRATEGY_HASH = 'hash';
export const STRATEGY_REWRITE = 'rewrite';

export type Strategy =
  | typeof STRATEGY_SUBSTITUTE
  | typeof STRATEGY_REDACT
  | typeof STRATEGY_ANNOTATE
  | typeof STRATEGY_HASH
  | typeof STRATEGY_REWRITE;

/** Rewrite is applied via `config.rewrite`; the other four via `config.replace`. */
export const REWRITE_STRATEGY: Strategy = STRATEGY_REWRITE;

export const STRATEGY_OPTIONS: { label: string; value: Strategy }[] = [
  { label: 'Substitute', value: STRATEGY_SUBSTITUTE },
  { label: 'Redact', value: STRATEGY_REDACT },
  { label: 'Annotate', value: STRATEGY_ANNOTATE },
  { label: 'Hash', value: STRATEGY_HASH },
  { label: 'Rewrite', value: STRATEGY_REWRITE },
];

export const STRATEGY_DESCRIPTIONS: Record<Strategy, string> = {
  [STRATEGY_SUBSTITUTE]:
    'Replace detected entities with LLM-generated synthetic values for names, cities, dates, etc.',
  [STRATEGY_REDACT]:
    'Replace entities with a label-based marker. The original text is removed entirely.',
  [STRATEGY_ANNOTATE]:
    'Tag entities with their label but preserve the original text. Useful for review and debugging.',
  [STRATEGY_HASH]:
    'Replace entities with a deterministic hash digest. The same entity text always produces the same hash.',
  [STRATEGY_REWRITE]:
    'Transform the entire text to produce a privacy-safe version that reduces explicit and inferable identifiers.',
};

export const ENTITY_MODE_CUSTOM = 'custom';
export const ENTITY_MODE_AUTO = 'auto';

export type EntityMode = typeof ENTITY_MODE_CUSTOM | typeof ENTITY_MODE_AUTO;

export const ENTITY_MODE_OPTIONS: { value: EntityMode; children: string }[] = [
  { value: ENTITY_MODE_CUSTOM, children: 'Custom' },
  { value: ENTITY_MODE_AUTO, children: 'Auto-detect' },
];

export const DEFAULT_PREVIEW_ROWS = 1;
