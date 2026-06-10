// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { JOB_SOURCE } from '@studio/components/dataViews/JobsDataView/constants';

export const CLAUDE_CODE_JOB_PROGRESS_TOOL_NAME = 'job_progress';
export const CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME = 'mcp__nemo_studio__job_progress';

export const JOB_PROGRESS_JOB_TYPE = {
  AGENT_EVALUATION: 'agent_evaluation',
  CUSTOMIZATION: 'customization',
  DATA_DESIGNER: 'data_designer',
  EVALUATOR: 'evaluator',
  SAFE_SYNTHESIZER: 'safe_synthesizer',
} as const;

export const JOB_PROGRESS_JOB_TYPE_SOURCE: Record<string, string> = {
  [JOB_PROGRESS_JOB_TYPE.CUSTOMIZATION]: JOB_SOURCE.CUSTOMIZATION,
  customizer: JOB_SOURCE.CUSTOMIZATION,
  [JOB_PROGRESS_JOB_TYPE.DATA_DESIGNER]: JOB_SOURCE.DATA_DESIGNER,
  'data-designer': JOB_SOURCE.DATA_DESIGNER,
  [JOB_PROGRESS_JOB_TYPE.SAFE_SYNTHESIZER]: JOB_SOURCE.SAFE_SYNTHESIZER,
  'safe-synthesizer': JOB_SOURCE.SAFE_SYNTHESIZER,
  [JOB_PROGRESS_JOB_TYPE.EVALUATOR]: JOB_SOURCE.EVALUATOR_METRICS,
  evaluation: JOB_SOURCE.EVALUATOR_METRICS,
  evaluator_metrics: JOB_SOURCE.EVALUATOR_METRICS,
  'evaluator-metrics': JOB_SOURCE.EVALUATOR_METRICS,
};
