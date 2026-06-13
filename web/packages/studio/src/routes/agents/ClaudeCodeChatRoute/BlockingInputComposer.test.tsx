// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getBlockingInputRequest } from '@studio/routes/agents/ClaudeCodeChatRoute/blockingInputRequest';
import type {
  ClaudeCodeInputRequest,
  ClaudeCodeInputRequestKind,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';

const makeRequest = (
  kind: ClaudeCodeInputRequestKind,
  input: Record<string, unknown> = {}
): ClaudeCodeInputRequest => ({
  requestId: 'request-1',
  kind,
  input,
});

describe('getBlockingInputRequest', () => {
  it.each([
    ['agent', 'Select an agent', 'Choose the agent the workflow should use.'],
    ['eval_config', 'Select an evaluation config', 'Choose a YAML file from a fileset.'],
    ['dataset_file', 'Select a dataset', 'Choose a dataset file from a fileset.'],
    ['model', 'Select a model', 'Choose the model this workflow should use.'],
  ] as const)('returns default copy for kind %s', (kind, expectedTitle, expectedDescription) => {
    expect(getBlockingInputRequest(makeRequest(kind))).toEqual({
      id: 'request-1',
      title: expectedTitle,
      description: expectedDescription,
    });
  });

  it('prefers caller-supplied title and description over defaults', () => {
    expect(
      getBlockingInputRequest(
        makeRequest('model', { title: 'Pick a judge', description: 'For LLM-as-judge scoring' })
      )
    ).toEqual({
      id: 'request-1',
      title: 'Pick a judge',
      description: 'For LLM-as-judge scoring',
    });
  });

  it('ignores blank caller-supplied strings and uses defaults', () => {
    expect(
      getBlockingInputRequest(makeRequest('agent', { title: '   ', description: '' }))
    ).toEqual({
      id: 'request-1',
      title: 'Select an agent',
      description: 'Choose the agent the workflow should use.',
    });
  });
});
