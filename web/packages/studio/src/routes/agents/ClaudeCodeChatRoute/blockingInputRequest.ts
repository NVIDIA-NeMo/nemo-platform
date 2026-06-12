// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getStringValue } from '@studio/components/agents/AgentBlockingInput/utils';
import type { ClaudeCodeInputRequest } from '@studio/routes/agents/ClaudeCodeChatRoute/types';

const DEFAULTS_BY_KIND: Record<
  ClaudeCodeInputRequest['kind'],
  { readonly title: string; readonly description: string }
> = {
  agent: {
    title: 'Select an agent',
    description: 'Choose the agent the workflow should use.',
  },
  eval_config: {
    title: 'Select an evaluation config',
    description: 'Choose a YAML file from a fileset.',
  },
  dataset_file: {
    title: 'Select a dataset',
    description: 'Choose a dataset file from a fileset.',
  },
  model: {
    title: 'Select a model',
    description: 'Choose the model this workflow should use.',
  },
};

export const getBlockingInputRequest = (request: ClaudeCodeInputRequest) => {
  const defaults = DEFAULTS_BY_KIND[request.kind];
  return {
    id: request.requestId,
    title: getStringValue(request.input, 'title') ?? defaults.title,
    description: getStringValue(request.input, 'description') ?? defaults.description,
  };
};
