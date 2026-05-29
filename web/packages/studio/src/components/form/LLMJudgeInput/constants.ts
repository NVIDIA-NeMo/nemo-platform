// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { buildModelConfig } from '@nemo/common/src/utils/models';
import { DEFAULT_MODEL_NAME } from '@studio/constants/constants';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import {
  ChatCompletionSystemMessageParam,
  ChatCompletionUserMessageParam,
} from 'openai/resources/index.mjs';

const defaultIdealMessage = 'The answer is accurate and complete.';
const defaultOutputText = 'The answer is mostly accurate.';

export interface LLMJudgeConfig {
  model: {
    api_endpoint: {
      url: string;
      model_id: string;
      format: 'nim';
    };
  };
  template: {
    messages: Array<ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam>;
  };
  scores: {
    [key: string]: {
      type: 'int' | 'float';
      parser: {
        type: 'regex';
        pattern: string;
      };
    };
  };
  [key: string]: unknown;
}

export interface AdvancedEvalSettingsFields {
  llmJudgeConfig: LLMJudgeConfig;
}

export const DEFAULT_LLM_JUDGE_CONFIG: LLMJudgeConfig = {
  model: buildModelConfig(DEFAULT_MODEL_NAME, PLATFORM_BASE_URL),
  template: {
    messages: [
      {
        role: 'system',
        content: 'Your task is to evaluate the semantic similarity between two responses.',
      },
      {
        role: 'user',
        content: `Respond in the following format SIMILARITY: 4.
        The similarity should be a score between 0 and 10.
        RESPONSE 1: ${defaultIdealMessage}
        RESPONSE 2: ${defaultOutputText}.
        `,
      },
    ],
  },
  scores: {
    llm_judge: {
      type: 'int',
      parser: {
        type: 'regex',
        pattern: 'SIMILARITY: (\\d{1,2})',
      },
    },
    similarity: {
      type: 'int',
      parser: {
        type: 'regex',
        pattern: 'SIMILARITY: (\\d*)',
      },
    },
  },
};
