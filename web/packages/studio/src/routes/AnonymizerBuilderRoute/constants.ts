// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RiskTolerance } from '@nemo/sdk/generated/anonymizer/schema';

export const SOURCE_TYPE_URL = 'url';
export const SOURCE_TYPE_DATASET = 'dataset';

export type SourceType = typeof SOURCE_TYPE_URL | typeof SOURCE_TYPE_DATASET;

export const SOURCE_TYPE_OPTIONS: { children: string; value: SourceType }[] = [
  { children: 'Dataset', value: SOURCE_TYPE_DATASET },
  { children: 'URL', value: SOURCE_TYPE_URL },
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

export const REWRITE_STRATEGY: Strategy = STRATEGY_REWRITE;

export const STRATEGY_OPTIONS: { children: string; value: Strategy }[] = [
  { children: 'Substitute', value: STRATEGY_SUBSTITUTE },
  { children: 'Redact', value: STRATEGY_REDACT },
  { children: 'Annotate', value: STRATEGY_ANNOTATE },
  { children: 'Hash', value: STRATEGY_HASH },
  { children: 'Rewrite', value: STRATEGY_REWRITE },
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

export const REDACT_DEFAULT_TEMPLATE = '[REDACTED_{label}]';
export const ANNOTATE_DEFAULT_TEMPLATE = '<{text}, {label}>';
export const HASH_DEFAULT_TEMPLATE = '<{label}_{digest}>';
export const HASH_DEFAULT_DIGEST_LENGTH = 8;

export const HASH_ALGORITHM_VALUES = ['sha256', 'sha1', 'md5'] as const;
export type HashAlgorithmOption = (typeof HASH_ALGORITHM_VALUES)[number];
export const HASH_ALGORITHM_DEFAULT: HashAlgorithmOption = 'sha256';
const HASH_ALGORITHM_LABELS: Record<HashAlgorithmOption, string> = {
  sha256: 'SHA-256',
  sha1: 'SHA-1',
  md5: 'MD5',
};
export const HASH_ALGORITHM_OPTIONS: { children: string; value: HashAlgorithmOption }[] =
  HASH_ALGORITHM_VALUES.map((value) => ({ children: HASH_ALGORITHM_LABELS[value], value }));

export const PRIVACY_GOAL_MODE_DEFAULT = 'default';
export const PRIVACY_GOAL_MODE_CUSTOM = 'custom';

export type PrivacyGoalMode = typeof PRIVACY_GOAL_MODE_DEFAULT | typeof PRIVACY_GOAL_MODE_CUSTOM;

export const PRIVACY_GOAL_MODE_OPTIONS: { value: PrivacyGoalMode; children: string }[] = [
  { value: PRIVACY_GOAL_MODE_DEFAULT, children: 'Default' },
  { value: PRIVACY_GOAL_MODE_CUSTOM, children: 'Custom' },
];

export const RISK_TOLERANCE_ORDER = [
  RiskTolerance.minimal,
  RiskTolerance.low,
  RiskTolerance.moderate,
  RiskTolerance.high,
] as const;

export const RISK_TOLERANCE_LABELS: Record<RiskTolerance, string> = {
  minimal: 'Minimal',
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
};

export const RISK_TOLERANCE_DEFAULT: RiskTolerance = RiskTolerance.low;
export const REWRITE_DEFAULT_MAX_REPAIR_ROUNDS = 3;
export const REWRITE_MIN_MAX_REPAIR_ROUNDS = 0;

export const ENTITY_MODE_CUSTOM = 'custom';
export const ENTITY_MODE_AUTO = 'auto';

export type EntityMode = typeof ENTITY_MODE_CUSTOM | typeof ENTITY_MODE_AUTO;

export const ENTITY_MODE_OPTIONS: { value: EntityMode; children: string }[] = [
  { value: ENTITY_MODE_CUSTOM, children: 'Custom' },
  { value: ENTITY_MODE_AUTO, children: 'Auto-detect' },
];

export const DEFAULT_PREVIEW_ROWS = 1;

export const MAX_COLUMN_INTROSPECTION_BYTES = 50 * 1024 * 1024;

export const DEFAULT_MODEL_TIMEOUT_SECONDS = 500;

export const DEFAULT_MODEL_MAX_TOKENS = 16384;

export const DETECTION_ROLES = [
  'entity_detector',
  'entity_validator',
  'entity_augmenter',
  'latent_detector',
];
export const REPLACE_ROLE = 'replacement_generator';
export const REWRITE_ROLES = [
  'domain_classifier',
  'disposition_analyzer',
  'meaning_extractor',
  'qa_generator',
  'rewriter',
  'repairer',
  'evaluator',
];

export const ROLE_LABELS: Record<string, string> = {
  entity_detector: 'Entity Detector',
  entity_validator: 'Entity Validator',
  entity_augmenter: 'Entity Augmenter',
  latent_detector: 'Latent Detector',
  replacement_generator: 'Replacement Generator',
  domain_classifier: 'Domain Classifier',
  disposition_analyzer: 'Disposition Analyzer',
  meaning_extractor: 'Meaning Extractor',
  qa_generator: 'QA Generator',
  rewriter: 'Rewriter',
  repairer: 'Repairer',
  evaluator: 'Evaluator',
};

export const GLINER_ROLE = 'entity_detector';

export const activeRolesForStrategy = (strategy: Strategy): string[] => {
  // rewrite reuses the replacement generator, so the backend validates that role too
  if (strategy === STRATEGY_REWRITE) return [...DETECTION_ROLES, ...REWRITE_ROLES, REPLACE_ROLE];
  if (strategy === STRATEGY_SUBSTITUTE) return [...DETECTION_ROLES, REPLACE_ROLE];
  return [...DETECTION_ROLES];
};
