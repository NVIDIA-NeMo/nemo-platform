// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { buildLLMJudgeChatPromptTemplate } from '@studio/components/evaluation/Jobs/form/utils';

describe('buildLLMJudgeChatPromptTemplate', () => {
  it('returns a chat messages prompt template with blank messages removed', () => {
    expect(
      buildLLMJudgeChatPromptTemplate([
        { role: 'system', content: ' Judge responses carefully. ' },
        { role: 'user', content: '' },
        { role: 'assistant', content: 'Use the rubric.' },
      ])
    ).toEqual({
      messages: [
        { role: 'system', content: ' Judge responses carefully. ' },
        { role: 'assistant', content: 'Use the rubric.' },
      ],
    });
  });

  it('returns null when no message has content', () => {
    expect(buildLLMJudgeChatPromptTemplate([{ role: 'user', content: '  ' }])).toBeNull();
  });
});
