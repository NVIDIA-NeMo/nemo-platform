// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { E2E_PROJECT_NAME, USER_ID } from '@e2e-tests/utils/environment';
import path from 'path';

export const E2E_NAMESPACE = 'default';
export const E2E_PROJECT_URL = `projects/${E2E_NAMESPACE}/${E2E_PROJECT_NAME}`;
export const E2E_MODELS_URL = `${E2E_PROJECT_URL}/models`;
export const E2E_DATASETS_URL = `${E2E_PROJECT_URL}/datasets`;
export const E2E_CUSTOMIZATIONS_URL = `${E2E_PROJECT_URL}/customizations`;

// Default model to use when creating a PromptTuned model
export const DEFAULT_BASE_MODEL = 'llama-3.2-3b-instruct';

// Platform: Training options are part of hyperparameters, not a separate type
export const DEFAULT_TRAINING_OPTIONS = {
  training_type: 'sft' as const,
  finetuning_type: 'lora' as const,
  num_gpus: 1,
  micro_batch_size: 1,
};

export const CURRENT_YYYY_MM_DD = new Date().toISOString().split('T')[0].replace(/-/g, '_');
export const YESTERDAY_YYYY_MM_DD = new Date(new Date().setDate(new Date().getDate() - 1))
  .toISOString()
  .split('T')[0]
  .replace(/-/g, '_');
export const CURRENT_HH_MM_SS = () =>
  new Date()
    .toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    .replace(/:/g, '_');

export const PROJECT_ROOT = process.cwd();
export const E2E_ROOT = path.join(PROJECT_ROOT, 'e2e-tests');
export const MOCKS_DIR = path.join(E2E_ROOT, 'mocks');

/**
 * Returns namespace to use when creating resources (ex. projects) for tests.
 * This is helpful for organizing test data for clean-up or debugging purposes.
 *
 * @param suffix Suffix to append to the namespace.
 */
export const buildTestNamespace = (suffix: string) => `e2e_${USER_ID || 'studio'}_${suffix}`;

/**
 * Generates a name for a test resource.
 *
 * @param resourceType Type of resource (ex. dataset, project, model)
 */
export const generateTestResourceName = (resourceType: string) =>
  `e2e_${resourceType}_${CURRENT_YYYY_MM_DD}_${CURRENT_HH_MM_SS()}`;

/**
 * Generates shortest unique name based on time. Example: e2e_0903093100 (e2e_MMDDHHMMSS)
 */
export const generateShortTestResourceName = () =>
  `e2e_${CURRENT_YYYY_MM_DD.split('_').slice(1).join('')}${CURRENT_HH_MM_SS().split('_').join('')}`;

// Simple timeout constants for long-running operations
export const LONG_OPERATION_TIMEOUT = 2 * 60 * 1000; // 2 minutes
export const VERY_LONG_OPERATION_TIMEOUT = 5 * 60 * 1000; // 5 minutes
