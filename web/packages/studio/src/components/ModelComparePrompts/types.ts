// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { SharedModelEntry } from '@studio/routes/ModelCompareRoute/types';

export interface ResponseStats {
  /** Wall-clock time from request fire to response, in ms. */
  totalMs: number;
  /** From `usage.completion_tokens` when the gateway returns it; otherwise estimated from text length. */
  completionTokens: number;
  /** Derived: completionTokens / (totalMs / 1000). */
  tokensPerSec: number;
}

export interface ResponseResult {
  text: string;
  stats: ResponseStats;
}

export interface PromptRow {
  /** Index in the parsed dataset. */
  sourceIndex: number;
  /** Resolved prompt text */
  prompt: string;
  /** Model id -> response data (null = error, undefined = not yet run) */
  responses: Record<number, ResponseResult | null | undefined>;
}

export interface ExpandedCellState {
  title: string;
  content: string;
  stats?: ResponseStats;
}

export interface ModelComparePromptsProps {
  workspace: string;
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels: boolean;
  models: SharedModelEntry[];
  onRemoveModel: (id: number) => void;
  onSetModel: (id: number, modelURN: string | null) => void;
  /** Called when the view's readiness to add models changes (i.e. file is loaded with a valid prompt key) */
  onReadyChange?: (ready: boolean) => void;
  /** Called when the user clicks the Add Model button. Omit to hide the button. */
  onAddModel?: () => void;
  /**
   * When set, default-select the matching `SAMPLE_DATASETS` entry on mount so
   * the user lands on the agent's golden-prompts dataset without a click.
   * Matching is by id equality (e.g. agent name "calculator-agent" matches the
   * "calculator-agent" sample). Other samples remain pickable.
   */
  agentName?: string | null;
}
