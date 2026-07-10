/*
 * SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  useCreateVirtualModel,
  useDeleteVirtualModel,
  useGetVirtualModel,
  useUpdateVirtualModel,
} from '@nemo/sdk/generated/platform/api';
import type { MiddlewareCall, VirtualModel } from '@nemo/sdk/generated/platform/schema';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

const TEST_VM_PREFIX = 'guardrail-test-';
const GUARDRAILS_PLUGIN = 'nemo-guardrails';
const GUARDRAIL_CONFIG_TYPE = 'guardrail_config';

/** Deterministic name of the feature-owned test VirtualModel for a config. */
export const getTestVmName = (configName: string): string => `${TEST_VM_PREFIX}${configName}`;

const vmReferencesConfig = (vm: VirtualModel | undefined, configId: string): boolean => {
  if (!vm) return false;
  const calls = [...(vm.request_middleware ?? []), ...(vm.response_middleware ?? [])];
  return calls.some((c) => c.name === GUARDRAILS_PLUGIN && c.config_id === configId);
};

export interface GuardrailTestVm {
  vmName: string;
  vm: VirtualModel | undefined;
  /** A VM with the derived name exists AND is wired to this config. */
  exists: boolean;
  /** A VM with the derived name exists but is wired to a DIFFERENT config. */
  conflict: boolean;
  isChecking: boolean;
  /** The model the VM currently routes to (`default_model_entity`). */
  boundModel: string | null;
  isMutating: boolean;
  create: (modelUrn: string) => Promise<void>;
  setModel: (modelUrn: string) => Promise<void>;
  remove: () => Promise<void>;
}

/**
 * Manages the feature-owned "test VM" for a guardrail config: a VirtualModel
 * whose only middleware applies this config's rails (in both the request and
 * response phases). The VM's `default_model_entity` is the generation target,
 * swappable via `setModel`. Config edits propagate to the VM automatically via
 * IGW's config-ref refresh, so the VM does not need updating when the config
 * changes.
 */
export const useGuardrailTestVm = (workspace: string, configName: string): GuardrailTestVm => {
  const queryClient = useQueryClient();
  const vmName = getTestVmName(configName);
  const configId = `${workspace}/${configName}`;

  const {
    data: vm,
    isPending,
    isError,
  } = useGetVirtualModel(workspace, vmName, {
    query: { enabled: Boolean(workspace && configName), retry: false },
  });

  const invalidate = useCallback(() => {
    const base = `/apis/inference-gateway/v2/workspaces/${workspace}/virtual-models`;
    return queryClient.invalidateQueries({
      predicate: (q) => typeof q.queryKey[0] === 'string' && q.queryKey[0].startsWith(base),
    });
  }, [queryClient, workspace]);

  const { mutateAsync: createVm, isPending: isCreating } = useCreateVirtualModel();
  const { mutateAsync: updateVm, isPending: isUpdating } = useUpdateVirtualModel();
  const { mutateAsync: deleteVm, isPending: isDeleting } = useDeleteVirtualModel();

  const create = useCallback(
    async (modelUrn: string) => {
      const call: MiddlewareCall = {
        name: GUARDRAILS_PLUGIN,
        config_type: GUARDRAIL_CONFIG_TYPE,
        config_id: configId,
      };
      await createVm({
        workspace,
        data: {
          name: vmName,
          default_model_entity: modelUrn,
          // Input rails run in the request phase, output rails in the response
          // phase — the same call must be listed in both pipelines.
          request_middleware: [call],
          response_middleware: [call],
        },
      });
      await invalidate();
    },
    [createVm, invalidate, workspace, vmName, configId]
  );

  const setModel = useCallback(
    async (modelUrn: string) => {
      await updateVm({ workspace, name: vmName, data: { default_model_entity: modelUrn } });
      await invalidate();
    },
    [updateVm, invalidate, workspace, vmName]
  );

  const remove = useCallback(async () => {
    await deleteVm({ workspace, name: vmName });
    await invalidate();
  }, [deleteVm, invalidate, workspace, vmName]);

  const found = !isPending && !isError && !!vm;
  const references = vmReferencesConfig(vm, configId);

  return {
    vmName,
    vm,
    exists: found && references,
    conflict: found && !references,
    isChecking: isPending,
    boundModel: vm?.default_model_entity ?? null,
    isMutating: isCreating || isUpdating || isDeleting,
    create,
    setModel,
    remove,
  };
};
