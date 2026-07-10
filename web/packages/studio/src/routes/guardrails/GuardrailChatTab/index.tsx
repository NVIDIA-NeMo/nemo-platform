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
import { useGuardrailsGetGuardrailConfig } from '@nemo/sdk/generated/platform/api';
import { Button, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { ParamsPopover } from '@studio/components/chat/ParamsPopover';
import { Loading } from '@studio/components/Layouts/Loading';
import { ModelChat } from '@studio/components/ModelChat';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useGuardrailTestVm } from '@studio/routes/guardrails/useGuardrailTestVm';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';

export const GuardrailChatTab: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  const testVm = useGuardrailTestVm(workspace, guardrailConfigName);

  // Config is only needed to seed the picker with the config's "main" model
  // (react-query dedupes with the layout's identical query).
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

  // Seed the picker once: prefer the existing VM's bound model, else the
  // config's "main" model when it maps to an available model.
  const didInitRef = useRef(false);
  useEffect(() => {
    if (didInitRef.current || testVm.isChecking || isLoadingModels) return;
    if (testVm.exists && testVm.boundModel) {
      setSelectedModel({ model: testVm.boundModel });
      didInitRef.current = true;
      return;
    }
    if (!testVm.exists) {
      const mainModelName = config?.data?.models?.find((m) => m.type === 'main')?.model;
      if (mainModelName) {
        const match = modelGroups
          .flatMap((g) => g.models)
          .find((m) => m.name === mainModelName || `${m.workspace}/${m.name}` === mainModelName);
        if (match) setSelectedModel({ model: `${match.workspace}/${match.name}` });
      }
      didInitRef.current = true;
    }
  }, [testVm.exists, testVm.boundModel, testVm.isChecking, isLoadingModels, config, modelGroups]);

  const handleModelChange = useCallback(
    (selection: ModelSelection) => {
      setSelectedModel(selection);
      // When the VM already exists, swapping the model repoints the VM.
      if (testVm.exists) {
        void testVm.setModel(selection.model);
      }
    },
    [testVm]
  );

  const handleCreate = useCallback(() => {
    if (selectedModel) void testVm.create(selectedModel.model);
  }, [selectedModel, testVm]);

  // The guardrails ride on the VM, so the chat targets the VM through the
  // canonical IGW openai proxy path (model = "workspace/<vm-name>").
  const baseURL = workspace
    ? `${PLATFORM_BASE_URL}/apis/inference-gateway/v2/workspaces/${workspace}/openai/-/v1`
    : undefined;

  return (
    <Stack className="min-h-0 flex-1 gap-density-md">
      <Flex className="shrink-0 items-center gap-density-sm">
        <div className="flex-1">
          <ModelSelectV2
            value={selectedModel}
            onValueChange={handleModelChange}
            groups={modelGroups}
            loading={isLoadingModels}
            hideAdapters
            fullWidth
            disabled={testVm.isMutating}
          />
        </div>
        <ParamsPopover value={inferenceParams} onChange={setInferenceParams} />
      </Flex>

      {testVm.isChecking ? (
        <Loading description="Checking for a test model..." />
      ) : testVm.conflict ? (
        <Text className="text-feedback-danger">
          A virtual model named &quot;{testVm.vmName}&quot; already exists but is not wired to this
          guardrail config. Remove or rename it to enable testing.
        </Text>
      ) : testVm.exists ? (
        <Stack className="min-h-0 flex-1 gap-density-xs">
          {testVm.isMutating ? (
            <Text kind="body/regular/sm" className="text-fg-subdued">
              Updating model… changes take a few seconds to take effect.
            </Text>
          ) : null}
          <div className="min-h-0 flex-1">
            <ModelChat
              // Remount (clears the thread) when the VM's target model changes.
              key={testVm.boundModel ?? testVm.vmName}
              model={`${workspace}/${testVm.vmName}`}
              workspace={workspace}
              baseURL={baseURL}
              // Guardrailed inference can return a non-streamed completion
              // (e.g. a blocked turn), which the streaming path renders empty.
              stream={false}
              assistantName={guardrailConfigName}
              disabled={testVm.isMutating}
              promptData={{ inference_params: inferenceParams }}
              seedQuestions={[]}
            />
          </div>
        </Stack>
      ) : (
        <Stack className="items-start gap-density-md">
          <Text kind="body/regular/md">
            Create a test model to chat with this guardrail config applied. Guardrails run around a
            model of your choice; config edits take effect automatically.
          </Text>
          <Button
            kind="primary"
            disabled={!selectedModel || testVm.isMutating}
            onClick={handleCreate}
          >
            {testVm.isMutating ? 'Creating…' : 'Create test model'}
          </Button>
        </Stack>
      )}
    </Stack>
  );
};
