// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { Pre } from '@studio/components/common/Pre';
import { ReadOnlyField } from '@studio/components/common/ReadOnlyField';
import { FC } from 'react';

const getStr = (params: Record<string, unknown> | undefined, key: string): string | undefined => {
  const val = params?.[key];
  return typeof val === 'string' ? val : undefined;
};

const getModelNameFromLLMJudgeParams = (params: Record<string, unknown> | undefined) =>
  getStr(params, 'model');
const getSystemMessageFromLLMJudgeParams = (params: Record<string, unknown> | undefined) =>
  getStr(params, 'system_message');
const getUserMessageFromLLMJudgeParams = (params: Record<string, unknown> | undefined) =>
  getStr(params, 'user_message');
const getScoreTypeFromLLMJudgeParams = (params: Record<string, unknown> | undefined) =>
  getStr(params, 'score_type');
const getParserPatternFromLLMJudgeParams = (params: Record<string, unknown> | undefined) =>
  getStr(params, 'parser_pattern');

export interface LLMJudgeDisplayProps {
  metricName: string;
  metricConfig: { type: string; params?: Record<string, unknown> };
}

/**
 * Component to display LLM-as-a-Judge metric details.
 * Shows the model, system/user messages, score type, and parser pattern.
 *
 * @param props.metricName - User-defined name for the metric
 * @param props.metricConfig - Metric configuration containing type and params
 */
export const LLMJudgeDisplay: FC<LLMJudgeDisplayProps> = ({ metricName, metricConfig }) => {
  const params = metricConfig.params;

  const modelName = getModelNameFromLLMJudgeParams(params);
  const systemMessage = getSystemMessageFromLLMJudgeParams(params);
  const userMessage = getUserMessageFromLLMJudgeParams(params);
  const scoreType = getScoreTypeFromLLMJudgeParams(params);
  const parserPattern = getParserPatternFromLLMJudgeParams(params);

  return (
    <Stack gap="density-2xl">
      <Text kind="label/bold/md">{metricName}</Text>
      <ReadOnlyField label="Type" value={metricConfig.type} />

      <Stack gap="density-2xl">
        <ReadOnlyField label="Model" value={modelName} />
        <ReadOnlyField
          label="System Message"
          value={systemMessage ? <Pre>{systemMessage}</Pre> : '-'}
        />
        <ReadOnlyField label="User Message" value={userMessage ? <Pre>{userMessage}</Pre> : '-'} />
      </Stack>

      <Stack gap="density-2xl">
        <ReadOnlyField label="Score Type" value={scoreType || '-'} />
        <ReadOnlyField label="Parser Pattern" value={parserPattern || '-'} />
      </Stack>
    </Stack>
  );
};
