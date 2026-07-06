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
  it('prefers the model-generated title over the first prompt', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          title: 'Restore Meaningful History Names',
          first_prompt:
            'The history panel currently shows a very long initial request that does not work well as a session name.',
        })
      )
    ).toBe('Restore Meaningful History Names');
  });

  it('turns a long contextual prompt into the latest actionable request', () => {
    expect(
      getHistorySessionTitle(
        makeSession({
          first_prompt:
            'On the evaluations dashboard, reviewers scan through dozens of saved runs every morning. The run cards include full agent notes and take up too much room. Is it possible for us to show compact outcome labels for faster triage?',
        })
      )
    ).toBe('Show compact outcome labels for faster triage');
  });

  it.each([
    [
      "When a new coding agent chat is started in Studio, can we make sure the empty text block with green edge doesn't show until there is content inside it? We still want to see the grey loading block.",
      'Hide the empty text block with green edge',
    ],
    [
      'When I am chatting, the messages get collapsed into one message block but after refresh they are separated into text and tool calls. Can we have them be separated even during chatting?',
      'Separate Live Chat Messages',
    ],
    [
      "When I select Generic on the create fileset page, I should be able to upload any type of file. Right now it doesn't allow a YAML file.",
      'Allow Any Generic Fileset Upload',
    ],
    [
      "We used to have the history panel's names summarized, but it seems there was a regression and we lost that functionality. Can we bring it back?",
      'Restore Summarized History Names',
    ],
    [
      "The history names aren't being summarized; they're just cut off. Can we provide a meaningful name instead of a truncated first message?",
      'Generate Meaningful History Names',
    ],
  ])('creates a useful legacy title for %s', (firstPrompt, expectedTitle) => {
    expect(getHistorySessionTitle(makeSession({ first_prompt: firstPrompt }))).toBe(expectedTitle);
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
