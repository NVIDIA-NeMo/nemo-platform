// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { USER_ID } from '@e2e-tests/utils/environment';
import crypto from 'crypto';
import path from 'path';

// Default model to use when creating a PromptTuned model
export const DEFAULT_BASE_MODEL = 'llama-3.2-3b-instruct';

// Full model ID with namespace for LLM-as-a-judge API calls
export const LLM_JUDGE_MODEL_ID = 'meta/llama-3.2-3b-instruct';

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

/**
 * Prefix for e2e workspace names, scoped by USER_ID so a run's `afterAll` cleanup
 * (deleteAllWorkspacesByPrefix) only removes its own workspaces — not those of a concurrent
 * run on a shared backend. `suffix` namespaces the prefix per suite so suites running in
 * parallel don't clean up each other's workspaces.
 */
export const buildTestWorkspacePrefix = (suffix: string) =>
  `e2e-wks-${USER_ID || 'studio'}-${suffix}-`;

/**
 * Generates a unique e2e workspace name for the given prefix. Combines a timestamp (for
 * readable debugging) with a random token so two workspaces created in the same second — or
 * across parallel workers — never collide.
 */
export const generateTestWorkspaceName = (prefix: string) =>
  `${prefix}${generateShortTestResourceName().replace('e2e_', '')}-${crypto.randomUUID().slice(0, 8)}`;

// Simple timeout constants for long-running operations
export const LONG_OPERATION_TIMEOUT = 2 * 60 * 1000; // 2 minutes
export const VERY_LONG_OPERATION_TIMEOUT = 5 * 60 * 1000; // 5 minutes
