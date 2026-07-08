// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getHistorySessionTitle } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/helpers';
import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeHistorySession,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';

const EMPTY_ARTIFACTS: ClaudeCodeChatArtifacts = {
  selections: [],
  files: [],
  links: [],
  jobs: [],
  tools: [],
};

const makeSession = ({
  chat_artifacts = EMPTY_ARTIFACTS,
  first_prompt = '',
  title,
}: {
  chat_artifacts?: ClaudeCodeChatArtifacts;
  first_prompt?: string;
  title?: string;
}): ClaudeCodeHistorySession => ({
  session_id: 'session-1',
  mtime: 0,
  title,
  first_prompt,
  message_count: first_prompt ? 1 : 0,
  token_count: 0,
  tool_call_count: 0,
  tool_calls: [],
  chat_artifacts,
});

describe('getHistorySessionTitle', () => {
  it('prefers a model-generated title over the first prompt', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          title: 'Create Spam Detector Agent',
          first_prompt: 'I want to create an agent that does spam detection for incoming email.',
        })
      )
    ).toBe('Create Spam Detector Agent');
  });

  it('creates an action-oriented legacy title for an agent creation prompt', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          first_prompt: 'I want to create an agent that does spam detection.',
        })
      )
    ).toBe('Create spam detector agent');
  });

  it('turns a long contextual prompt into the latest actionable request', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          first_prompt:
            'Reviewers scan dozens of saved runs every morning. The cards take up too much room. Can we show compact outcome labels for faster triage?',
        })
      )
    ).toBe('Show compact outcome labels for faster triage');
  });

  it('falls back to artifacts when no prompt is available', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          chat_artifacts: { ...EMPTY_ARTIFACTS, agent: 'beach-finder' },
        })
      )
    ).toBe('Agent beach-finder');
  });
});
