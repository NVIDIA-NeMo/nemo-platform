// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import {
  mockEvalConfigCustom,
  mockEvalConfigCustomMultiTask,
} from '@studio/mocks/evaluation/configs';
import {
  type EvaluationConfig,
  getCustomConfigTaskByName,
  getCustomConfigTaskEntries,
  getCustomConfigTaskNames,
  getFirstCustomConfigTask,
  getTaskDataset,
  getTaskFilesetInfo,
  getTaskFilesets,
  getTaskDatasetFilesUrl,
  getTaskMetrics,
  getTaskMetricsArray,
  getTaskTargetTypeDisplay,
  getTaskType,
  type TaskConfigInput,
} from '@studio/selectors/evaluationConfig';

describe('evaluationConfig selectors', () => {
  describe('Multi-Task Selectors for Custom Configs', () => {
    describe('getCustomConfigTaskNames', () => {
      it('should return all task names from a multi-task config', () => {
        const taskNames = getCustomConfigTaskNames(mockEvalConfigCustomMultiTask);
        expect(taskNames).toEqual(['llm-task', 'data-quality-task', 'similarity-task']);
      });

      it('should return single task name from a single-task config', () => {
        const taskNames = getCustomConfigTaskNames(mockEvalConfigCustom);
        expect(taskNames).toEqual(['default']);
      });

      it('should return empty array when no tasks exist', () => {
        const taskNames = getCustomConfigTaskNames({
          type: 'custom',
          tasks: {},
        } as EvaluationConfig);
        expect(taskNames).toEqual([]);
      });
    });

    describe('getCustomConfigTaskEntries', () => {
      it('should return all tasks as array of tuples from a multi-task config', () => {
        const tasks = getCustomConfigTaskEntries(mockEvalConfigCustomMultiTask);
        expect(tasks).toHaveLength(3);
        expect(tasks[0][0]).toBe('llm-task');
        expect(tasks[0][1].type).toBe('chat-completion');
        expect(tasks[1][0]).toBe('data-quality-task');
        expect(tasks[1][1].type).toBe('data');
        expect(tasks[2][0]).toBe('similarity-task');
        expect(tasks[2][1].type).toBe('default');
      });

      it('should return single task as array from a single-task config', () => {
        const tasks = getCustomConfigTaskEntries(mockEvalConfigCustom);
        expect(tasks).toHaveLength(1);
        expect(tasks[0][0]).toBe('default');
        expect(tasks[0][1].type).toBe('humaneval');
      });
    });

    describe('getCustomConfigTaskByName', () => {
      it('should return specific task by name from multi-task config', () => {
        const task = getCustomConfigTaskByName(mockEvalConfigCustomMultiTask, 'llm-task');
        expect(task).toBeDefined();
        expect(task?.type).toBe('chat-completion');
      });

      it('should return undefined for non-existent task name', () => {
        const task = getCustomConfigTaskByName(mockEvalConfigCustomMultiTask, 'non-existent');
        expect(task).toBeUndefined();
      });

      it('should return default task from single-task config', () => {
        const task = getCustomConfigTaskByName(mockEvalConfigCustom, 'default');
        expect(task).toBeDefined();
        expect(task?.type).toBe('humaneval');
      });
    });

    describe('getFirstCustomConfigTask', () => {
      it('should return first task from multi-task config', () => {
        const firstTask = getFirstCustomConfigTask(mockEvalConfigCustomMultiTask);
        expect(firstTask).toBeDefined();
        expect(firstTask![0]).toBe('llm-task');
        expect(firstTask![1].type).toBe('chat-completion');
      });

      it('should return the only task from single-task config', () => {
        const firstTask = getFirstCustomConfigTask(mockEvalConfigCustom);
        expect(firstTask).toBeDefined();
        expect(firstTask![0]).toBe('default');
        expect(firstTask![1].type).toBe('humaneval');
      });

      it('should return undefined when no tasks exist', () => {
        const firstTask = getFirstCustomConfigTask({
          type: 'custom',
          tasks: {},
        } as EvaluationConfig);
        expect(firstTask).toBeUndefined();
      });
    });
  });

  describe('Task-Level Helper Functions', () => {
    const llmTask = mockEvalConfigCustomMultiTask.tasks['llm-task'];
    const dataTask = mockEvalConfigCustomMultiTask.tasks['data-quality-task'];

    describe('getTaskType', () => {
      it('should return task type', () => {
        expect(getTaskType(llmTask)).toBe('chat-completion');
        expect(getTaskType(dataTask)).toBe('data');
      });

      it('should return undefined for undefined task', () => {
        expect(getTaskType(undefined)).toBeUndefined();
      });
    });

    describe('getTaskDataset', () => {
      it('should return dataset object', () => {
        const dataset = getTaskDataset(llmTask);
        expect(dataset).toBeDefined();
        expect(dataset).toHaveProperty('files_url');
      });

      it('should return undefined for task without dataset', () => {
        const taskWithoutDataset = { type: 'test' } as TaskConfigInput;
        expect(getTaskDataset(taskWithoutDataset)).toBeUndefined();
      });
    });

    describe('getTaskDatasetFilesUrl', () => {
      it('should return files_url from dataset object', () => {
        const input = getTaskDatasetFilesUrl(llmTask);
        expect(input).toBe('hf://datasets/test-user/llm-dataset/data.jsonl');
      });

      it('should return string dataset directly', () => {
        const taskWithStringDataset = {
          type: 'test',
          dataset: 'path/to/file.json',
        } as TaskConfigInput;
        const input = getTaskDatasetFilesUrl(taskWithStringDataset);
        expect(input).toBe('path/to/file.json');
      });

      it('should return undefined for task without dataset', () => {
        expect(getTaskDatasetFilesUrl(undefined)).toBeUndefined();
      });
    });

    describe('getTaskMetrics', () => {
      it('should return metrics object', () => {
        const metrics = getTaskMetrics(llmTask);
        expect(metrics).toBeDefined();
        expect(metrics).toHaveProperty('llm-judge');
        expect(metrics).toHaveProperty('bleu');
      });

      it('should return empty object for task without metrics', () => {
        const metrics = getTaskMetrics(undefined);
        expect(metrics).toEqual({});
      });
    });

    describe('getTaskMetricsArray', () => {
      it('should return metrics as array of names', () => {
        const metrics = getTaskMetricsArray(llmTask);
        expect(metrics).toContain('llm-judge');
        expect(metrics).toContain('bleu');
        expect(metrics).toHaveLength(2);
      });

      it('should return empty array for task without metrics', () => {
        const metrics = getTaskMetricsArray(undefined);
        expect(metrics).toEqual([]);
      });
    });

    describe('getTaskTargetTypeDisplay', () => {
      it('should return "LLM Model" for chat-completion task', () => {
        expect(getTaskTargetTypeDisplay(llmTask)).toBe('LLM Model');
      });

      it('should return "Data Source" for data task', () => {
        expect(getTaskTargetTypeDisplay(dataTask)).toBe('Data Source');
      });

      it('should return task type for other types', () => {
        const task = { type: 'custom-type' } as TaskConfigInput;
        expect(getTaskTargetTypeDisplay(task)).toBe('custom-type');
      });

      it('should return "-" for undefined task', () => {
        expect(getTaskTargetTypeDisplay(undefined)).toBe('-');
      });
    });

    describe('getTaskFilesetInfo', () => {
      it('should parse HuggingFace fileset URL and return structured data with linkUrl', () => {
        const tasks = getCustomConfigTaskEntries(mockEvalConfigCustomMultiTask);
        const [taskName, task] = tasks[0];
        const filesetInfo = getTaskFilesetInfo(taskName, task, DEFAULT_WORKSPACE);

        expect(filesetInfo).toEqual({
          taskName: 'llm-task',
          filesetId: 'test-user/llm-dataset',
          filePath: 'data.jsonl',
          fileDisplayName: 'llm-dataset/data.jsonl',
          linkUrl: expect.stringContaining(
            `/workspaces/${DEFAULT_WORKSPACE}/filesets/${encodeURIComponent('test-user/llm-dataset')}/file/data.jsonl`
          ),
        });
      });

      it('should return undefined when task has no fileset', () => {
        const task = { type: 'chat-completion' } as TaskConfigInput;
        const filesetInfo = getTaskFilesetInfo('task1', task, DEFAULT_WORKSPACE);
        expect(filesetInfo).toBeUndefined();
      });

      it('should return undefined for non-HuggingFace URL formats', () => {
        const task = { type: 'test', dataset: 'simple-string' } as TaskConfigInput;
        const filesetInfo = getTaskFilesetInfo('task1', task, DEFAULT_WORKSPACE);
        expect(filesetInfo).toBeUndefined();
      });
    });

    describe('getTaskFilesets', () => {
      it('should parse HuggingFace fileset URLs and return structured data with linkUrl', () => {
        const tasks = getCustomConfigTaskEntries(mockEvalConfigCustomMultiTask);
        const filesets = getTaskFilesets(tasks, DEFAULT_WORKSPACE);

        expect(filesets).toHaveLength(3);
        expect(filesets[0]).toEqual({
          taskName: 'llm-task',
          filesetId: 'test-user/llm-dataset',
          filePath: 'data.jsonl',
          fileDisplayName: 'llm-dataset/data.jsonl',
          linkUrl: expect.stringContaining(
            `/workspaces/${DEFAULT_WORKSPACE}/filesets/${encodeURIComponent('test-user/llm-dataset')}/file/data.jsonl`
          ),
        });
      });

      it('should return empty array when no filesets have files_url', () => {
        const tasks: ReturnType<typeof getCustomConfigTaskEntries> = [
          ['task1', { type: 'chat-completion' } as TaskConfigInput],
        ];
        const filesets = getTaskFilesets(tasks, DEFAULT_WORKSPACE);
        expect(filesets).toEqual([]);
      });

      it('should skip tasks with non-HuggingFace URL formats', () => {
        const tasks: ReturnType<typeof getCustomConfigTaskEntries> = [
          ['task1', { type: 'test', dataset: 'simple-string' } as TaskConfigInput],
        ];
        const filesets = getTaskFilesets(tasks, DEFAULT_WORKSPACE);
        expect(filesets).toEqual([]);
      });
    });
  });
});
