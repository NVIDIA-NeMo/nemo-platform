// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getHistorySessionTitle } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/helpers';
import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeHistorySession,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';

const emptyArtifacts: ClaudeCodeChatArtifacts = {
  selections: [],
  files: [],
  links: [],
  jobs: [],
  tools: [],
};

const makeSession = ({
  chat_artifacts = emptyArtifacts,
  first_prompt = '',
}: {
  chat_artifacts?: ClaudeCodeChatArtifacts;
  first_prompt?: string;
}): ClaudeCodeHistorySession => ({
  session_id: 'session-1',
  mtime: 0,
  first_prompt,
  message_count: first_prompt ? 1 : 0,
  token_count: 0,
  tool_call_count: 0,
  tool_calls: [],
  chat_artifacts,
});

describe('getHistorySessionTitle', () => {
  it('turns a long contextual prompt into the latest actionable request', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          first_prompt:
            "In our coding agent interface in Studio (which I already have running) we currently have a chat history panel. The chats in this panel have very long wordy names - we're pulling them from our coding agent directly. Is it possible for us to give them concise relevant names to improve chat discovery?",
        })
      )
    ).toBe('Give concise relevant names to improve chat discovery');
  });

  it('keeps direct prompts readable', () => {
    expect(
      getHistorySessionTitle(makeSession({ first_prompt: 'Review the latest agent work' }))
    ).toBe('Review the latest agent work');
  });

  it('removes request framing from one-sentence prompts', () => {
    expect(
      getHistorySessionTitle(
        makeSession({ first_prompt: 'Can you please review the latest agent work?' })
      )
    ).toBe('Review the latest agent work');
  });

  it('falls back to artifacts when no prompt is available', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          chat_artifacts: {
            ...emptyArtifacts,
            agent: 'beach-finder',
          },
        })
      )
    ).toBe('Agent beach-finder');
  });
});
