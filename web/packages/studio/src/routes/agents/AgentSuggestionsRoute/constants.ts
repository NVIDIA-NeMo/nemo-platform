// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvalJobStatus } from '@studio/routes/agents/AgentSuggestionsRoute/types';

export const EVAL_STATUS_LABEL: Record<EvalJobStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  unknown: 'Unknown',
};

export const EVAL_STATUS_COLOR: Record<EvalJobStatus, 'gray' | 'green' | 'red' | 'blue'> = {
  queued: 'gray',
  running: 'blue',
  completed: 'green',
  failed: 'red',
  cancelled: 'gray',
  unknown: 'gray',
};

export const SCOPE_AGENT = 'agent';
export const SCOPE_WORKSPACE = 'workspace';

export const SCOPE_OPTIONS = [
  { value: SCOPE_AGENT, label: 'Agent-specific' },
  { value: SCOPE_WORKSPACE, label: 'Workspace-wide' },
];

export const TYPE_OPTIONS = [
  { value: 'model_optimization', label: 'Model Optimization' },
  { value: 'guardrails', label: 'Guardrails' },
  { value: 'data_safety', label: 'Data Safety' },
  { value: 'new_model_scan', label: 'New Model' },
];

export const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

export const STALE_SUGGESTION_MS = 7 * 24 * 60 * 60 * 1000;
