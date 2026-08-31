// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Block, Flex, Stack } from '@nvidia/foundations-react-core';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { ParamsPopover } from '@studio/components/chat/ParamsPopover';
import { ModelChat } from '@studio/components/ModelChat';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, useState } from 'react';

export const VirtualModelChatTab: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { virtualModelName } = useRequiredPathParams([ROUTE_PARAMS.virtualModelName]);

  const [inferenceParams, setInferenceParams] = useState<InferenceParams>({
    ...DEFAULT_INFERENCE_PARAMS,
    max_tokens: 4096,
  });

  return (
    <Stack className="min-h-0 flex-1">
      <Flex align="center" justify="end" className="shrink-0 border-b border-base pb-3">
        <ParamsPopover value={inferenceParams} onChange={setInferenceParams} />
      </Flex>
      <Block className="h-full min-h-0 pt-4">
        <ModelChat
          key={`${workspace}/${virtualModelName}`}
          model={virtualModelName}
          workspace={workspace}
          assistantName={virtualModelName}
          promptData={{ inference_params: inferenceParams }}
        />
      </Block>
    </Stack>
  );
};
