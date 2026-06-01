// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MetricNameApi } from '@nemo/common/src/constants/metrics';
import { getFilesetFileRoute } from '@studio/routes/utils';
import { getDatasetDisplayNameFromFilesUrl } from '@studio/util/files';

/** Evaluation config shape used by custom config selectors (tasks, params, type). */
export interface EvaluationConfig {
  id?: string;
  type?: string;
  name?: string;
  workspace?: string;
  description?: string;
  created_at?: string;
  params?: Record<string, unknown> & { extra?: Record<string, unknown> };
  tasks?: Record<string, TaskConfigInput>;
  custom_fields?: Record<string, unknown>;
}

/** Single task config within an evaluation config. */
export interface TaskConfigInput {
  type?: string;
  dataset?: string | { files_url?: string };
  metrics?: Record<string, { type?: string }>;
}

export const getConfigId = (config: EvaluationConfig) => {
  return config?.id;
};

export const getConfigType = (config: EvaluationConfig) => {
  return config?.type;
};

export const getConfigDisplayName = (config: EvaluationConfig) => {
  return config?.name;
};

export const getConfigName = (config: EvaluationConfig) => {
  return config?.name;
};

export const getConfigNamespace = (config: EvaluationConfig) => {
  return config?.workspace;
};

export const getConfigDescription = (config: EvaluationConfig) => {
  return config?.description;
};

export const getConfigParams = (config: EvaluationConfig) => {
  return config?.params || {};
};

export const getConfigTasks = (config: EvaluationConfig) => {
  return config?.tasks || {};
};

// ============================================================================
// Multi-Task Selectors for Custom Configs
// Note: Only custom configs (type: 'custom') support multiple tasks.
// Configs with other types are "academic" configs and are not currently supported.
// ============================================================================

/**
 * Get all task names from a custom config
 */
export const getCustomConfigTaskNames = (config: EvaluationConfig): string[] => {
  return Object.keys(config?.tasks || {});
};

/**
 * Get all tasks as [name, task] entries from a custom config
 * Returns an array of tuples, similar to Object.entries()
 */
export const getCustomConfigTaskEntries = (
  config: EvaluationConfig
): Array<[string, TaskConfigInput]> => {
  const tasks = config?.tasks || {};
  return Object.entries(tasks);
};

/**
 * Get a specific task by name from a custom config
 */
export const getCustomConfigTaskByName = (
  config: EvaluationConfig,
  taskName: string
): TaskConfigInput | undefined => {
  return config?.tasks?.[taskName];
};

/**
 * Get the first task from a custom config (useful for configs with only one task)
 * Returns the task and its name as a tuple [name, task]
 */
export const getFirstCustomConfigTask = (
  config: EvaluationConfig
): [string, TaskConfigInput] | undefined => {
  const tasks = getCustomConfigTaskEntries(config);
  return tasks.length > 0 ? tasks[0] : undefined;
};

export const getConfigCustomFields = (config: EvaluationConfig) => {
  return Object.keys(config?.custom_fields || {}) || [];
};

// ============================================================================
// Task-Level Helper Functions
// These work on individual TaskConfigInput objects and can be used with
// tasks from custom configs. They are not config-type specific.
// ============================================================================

/**
 * Get task type for a specific task
 */
export const getTaskType = (task: TaskConfigInput | undefined): string | undefined => {
  return task?.type;
};

/**
 * Get dataset from a specific task
 */
export const getTaskDataset = (task: TaskConfigInput | undefined) => {
  return task?.dataset;
};

/**
 * Get dataset files_url (string or files_url) from a task
 */
export const getTaskDatasetFilesUrl = (task: TaskConfigInput | undefined): string | undefined => {
  const dataset = getTaskDataset(task);
  return typeof dataset === 'string' ? dataset : dataset?.files_url;
};

/**
 * Get metrics from a specific task
 */
export const getTaskMetrics = (task: TaskConfigInput | undefined) => {
  return task?.metrics || {};
};

/**
 * Get metrics as an array for a specific task
 */
export const getTaskMetricsArray = (task: TaskConfigInput | undefined): MetricNameApi[] => {
  const metrics = getTaskMetrics(task);
  return Object.values(metrics).map((m: { type?: string }) => m.type as MetricNameApi);
};

/**
 * Get target type display label for a task
 */
export const getTaskTargetTypeDisplay = (task: TaskConfigInput | undefined): string => {
  const taskType = getTaskType(task);
  if (!taskType) return '-';

  // Map task types to target type labels
  if (taskType === 'chat-completion') return 'LLM Model';
  if (taskType === 'data') return 'Data Source';

  // Fallback to the raw task type
  return taskType;
};

export interface TaskFilesetInfo {
  taskName: string;
  filesetId: string;
  filePath: string;
  fileDisplayName: string;
  linkUrl: string;
}

/**
 * Extract fileset information from a single task for display and linking.
 * Parses fileset URLs in multiple formats:
 * - HuggingFace: hf://datasets/namespace/fileset-name/path/to/file.jsonl
 * - NDS: nds:namespace/fileset-name/path/to/file.jsonl
 *
 * @param taskName - Name of the task
 * @param task - Task configuration object
 * @param workspace - workspace reference for generating fileset file routes
 * @returns Parsed fileset information including linkUrl for navigation, or undefined if no valid fileset
 */
export const getTaskFilesetInfo = (
  taskName: string,
  task: TaskConfigInput,
  workspace: string
): TaskFilesetInfo | undefined => {
  const filesUrl = getTaskDatasetFilesUrl(task);
  if (!filesUrl) return undefined;

  // Parse the fileset URL to extract fileset ID and file path
  const urlWithoutProtocol = filesUrl.replace(/^[a-z]+:\/\/|^[a-z]+:/, '');
  const parts = urlWithoutProtocol.split('/');

  // For HuggingFace URLs: hf://datasets/namespace/fileset-name/path/to/file.jsonl
  // Format after removing protocol: datasets/namespace/fileset-name/path/to/file.jsonl
  if (parts.length >= 4 && parts[0] === 'datasets') {
    const filesetId = `${parts[1]}/${parts[2]}`; // namespace/fileset-name
    const filePath = parts.slice(3).join('/'); // path/to/file.jsonl
    const fileDisplayName = getDatasetDisplayNameFromFilesUrl(filesUrl);
    if (!fileDisplayName) return undefined;

    const linkUrl = getFilesetFileRoute(workspace, filesetId, filePath);
    return { taskName, filesetId, filePath, fileDisplayName, linkUrl };
  }

  // For NDS URLs: nds:namespace/fileset-name/path/to/file.jsonl
  // Format after removing protocol: namespace/fileset-name/path/to/file.jsonl
  if (parts.length >= 3) {
    const filesetId = `${parts[0]}/${parts[1]}`; // namespace/fileset-name
    const filePath = parts.slice(2).join('/'); // path/to/file.jsonl
    const fileDisplayName = getDatasetDisplayNameFromFilesUrl(filesUrl);
    if (!fileDisplayName) return undefined;

    const linkUrl = getFilesetFileRoute(workspace, filesetId, filePath);
    return { taskName, filesetId, filePath, fileDisplayName, linkUrl };
  }

  return undefined;
};

/**
 * Extract fileset information from multiple tasks for display and linking.
 * Parses HuggingFace-style URLs for each task and returns an array of structured data.
 *
 * @param tasks - Array of task entries from getCustomConfigTaskEntries
 * @param workspace - workspace reference for generating fileset file routes
 * @returns Array of parsed fileset information including linkUrl for navigation
 */
export const getTaskFilesets = (
  tasks: ReturnType<typeof getCustomConfigTaskEntries>,
  workspace: string
): TaskFilesetInfo[] => {
  return tasks.reduce((acc, [taskName, task]) => {
    const filesetInfo = getTaskFilesetInfo(taskName, task, workspace);
    if (filesetInfo) {
      acc.push(filesetInfo);
    }
    return acc;
  }, [] as TaskFilesetInfo[]);
};

// Utilities to determine config type for workflows
// TODO: add LLM as a judge to this check when schema is conformed
export const isCustomConfig = (config: EvaluationConfig) => {
  return config.type === 'custom';
};
