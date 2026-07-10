/*
 * SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  BASIC_ALL_MODELS_DROPDOWN_FILTER,
  buildWorkspaceGroup,
  type ModelWorkspaceGroup,
  useAllModels,
} from '@nemo/common/src/api/models/useModels';
import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { PLATFORM_BASE_URL } from '@nemo/common/src/constants/environment';
import { useGuardrailsGetGuardrailConfig } from '@nemo/sdk/generated/platform/api';
import { Flex, Stack } from '@nvidia/foundations-react-core';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { ParamsPopover } from '@studio/components/chat/ParamsPopover';
import { ModelChat } from '@studio/components/ModelChat';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, useEffect, useMemo, useRef, useState } from 'react';

export const GuardrailChatTab: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  // Own clean fetch — react-query dedupes with the layout's identical query.
  // Used only to default the model picker to the config's "main" model.
  const { data: config } = useGuardrailsGetGuardrailConfig(workspace, guardrailConfigName, {
    query: { enabled: Boolean(workspace && guardrailConfigName) },
  });

  const { data: modelsData, isFetching: isLoadingModels } = useAllModels({
    workspace: workspace ?? undefined,
    query: BASIC_ALL_MODELS_DROPDOWN_FILTER,
  });

  const modelGroups = useMemo((): ModelWorkspaceGroup[] => {
    if (!workspace) return [];
    const allModels = modelsData?.pages.flatMap((p) => (Array.isArray(p.data) ? p.data : [])) ?? [];
    const available = allModels.filter(
      (m) => Array.isArray(m.model_providers) && m.model_providers.length > 0
    );
    return available.length > 0 ? [buildWorkspaceGroup(workspace, available)] : [];
  }, [modelsData, workspace]);

  const [selectedModel, setSelectedModel] = useState<ModelSelection | null>(null);
  const [inferenceParams, setInferenceParams] = useState<InferenceParams>(DEFAULT_INFERENCE_PARAMS);

  // Best-effort default: preselect the config's "main" model once models load,
  // if that model is present in this workspace's list. The main model is a
  // placeholder in some configs (no name), in which case the user picks.
  const didPreselectRef = useRef(false);
  useEffect(() => {
    if (didPreselectRef.current || isLoadingModels || modelGroups.length === 0) return;
    const mainModelName = config?.data?.models?.find((m) => m.type === 'main')?.model;
    if (mainModelName) {
      const match = modelGroups
        .flatMap((g) => g.models)
        .find((m) => m.name === mainModelName || `${m.workspace}/${m.name}` === mainModelName);
      if (match) setSelectedModel({ model: `${match.workspace}/${match.name}` });
    }
    didPreselectRef.current = true;
  }, [config, isLoadingModels, modelGroups]);

  // The guardrails chat endpoint takes the target model as a Model Entity
  // reference ("workspace/model_name") in the request body's `model` field.
  const modelURN = selectedModel?.model ?? null;

  // Route the OpenAI-compatible client at the standalone guardrails chat
  // endpoint: the client appends "/chat/completions" to this base URL.
  const baseURL = workspace
    ? `${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/${workspace}`
    : undefined;

  // Apply this config's rails around the completion.
  const bodyExtra = useMemo(
    () => ({ guardrails: { config_ids: [`${workspace}/${guardrailConfigName}`] } }),
    [workspace, guardrailConfigName]
  );

  return (
    <Stack className="min-h-0 flex-1 gap-density-md">
      <Flex className="shrink-0 items-center gap-density-sm">
        <div className="flex-1">
          <ModelSelectV2
            value={selectedModel}
            onValueChange={(selection) => setSelectedModel(selection)}
            groups={modelGroups}
            loading={isLoadingModels}
            hideAdapters
            fullWidth
          />
        </div>
        <ParamsPopover value={inferenceParams} onChange={setInferenceParams} />
      </Flex>

      <Stack className="min-h-0 flex-1">
        <ModelChat
          // Remount (clears thread) when the selected model changes.
          key={modelURN ?? 'none'}
          model={modelURN ?? ''}
          workspace={workspace}
          baseURL={baseURL}
          bodyExtra={bodyExtra}
          disabled={!modelURN}
          emptyState={!modelURN ? { slotHeading: 'Select a model to start chatting' } : undefined}
          promptData={{ inference_params: inferenceParams }}
          seedQuestions={[]}
        />
      </Stack>
    </Stack>
  );
};
