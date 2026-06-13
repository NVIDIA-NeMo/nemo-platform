// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  filesCreateFileset,
  modelsCreateDeployment,
  modelsCreateDeploymentConfig,
  modelsCreateModel,
} from '@nemo/sdk/generated/platform/api';
import {
  defaultWizardValues,
  WORKSPACE_PICKER_FILESET,
  WORKSPACE_PICKER_MODEL,
  SOURCE_WORKSPACE,
  type WizardFormValues,
} from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/schema';
import { useCreateDeploymentBySource } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/useCreateDeploymentBySource';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { type ReactNode } from 'react';

vi.mock('@nemo/common/src/providers/toast/useToast');
vi.mock('@nemo/sdk/generated/platform/api');

const mockUseToast = vi.mocked(useToast);
const mockFilesCreateFileset = vi.mocked(filesCreateFileset);
const mockModelsCreateModel = vi.mocked(modelsCreateModel);
const mockModelsCreateDeploymentConfig = vi.mocked(modelsCreateDeploymentConfig);
const mockModelsCreateDeployment = vi.mocked(modelsCreateDeployment);

const workspace = 'ws';

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function baseWorkspaceValues(overrides: Partial<WizardFormValues> = {}): WizardFormValues {
  return {
    ...defaultWizardValues(),
    source: SOURCE_WORKSPACE,
    name: 'my-deploy',
    gpu: 2,
    ...overrides,
  };
}

describe('useCreateDeploymentBySource — workspace source', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseToast.mockReturnValue({
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
      workingWithId: vi.fn(),
      dismissToast: vi.fn(),
    } as unknown as ReturnType<typeof useToast>);

    mockFilesCreateFileset.mockResolvedValue(undefined as never);
    mockModelsCreateModel.mockResolvedValue(undefined as never);
    mockModelsCreateDeploymentConfig.mockResolvedValue(undefined as never);
    mockModelsCreateDeployment.mockResolvedValue(undefined as never);
  });

  it('deploys an existing model entity without creating a fileset or model', async () => {
    const { result } = renderHook(() => useCreateDeploymentBySource(workspace), { wrapper });
    const onSuccess = vi.fn();

    await act(async () => {
      await result.current.createDeploymentFromWizard(
        baseWorkspaceValues({
          workspacePickerType: WORKSPACE_PICKER_MODEL,
          modelRef: 'other-ws/existing-model',
        }),
        onSuccess
      );
    });

    expect(mockFilesCreateFileset).not.toHaveBeenCalled();
    expect(mockModelsCreateModel).not.toHaveBeenCalled();

    expect(mockModelsCreateDeploymentConfig).toHaveBeenCalledWith(workspace, {
      name: 'my-deploy-config',
      engine: 'nim',
      model_spec: {
        model_namespace: 'other-ws',
        model_name: 'existing-model',
      },
      executor_config: {
        gpu: 2,
      },
      model_entity_id: 'other-ws/existing-model',
    });

    expect(mockModelsCreateDeployment).toHaveBeenCalledWith(workspace, {
      name: 'my-deploy-deployment',
      config: 'my-deploy-config',
    });

    expect(onSuccess).toHaveBeenCalled();
  });

  it('registers a model entity from the selected fileset before deploying', async () => {
    const { result } = renderHook(() => useCreateDeploymentBySource(workspace), { wrapper });
    const onSuccess = vi.fn();

    await act(async () => {
      await result.current.createDeploymentFromWizard(
        baseWorkspaceValues({
          workspacePickerType: WORKSPACE_PICKER_FILESET,
          fileset: 'other-ws/some-fileset',
        }),
        onSuccess
      );
    });

    expect(mockFilesCreateFileset).not.toHaveBeenCalled();

    expect(mockModelsCreateModel).toHaveBeenCalledWith(workspace, {
      name: 'my-deploy',
      fileset: 'other-ws/some-fileset',
    });

    expect(mockModelsCreateDeploymentConfig).toHaveBeenCalledWith(workspace, {
      name: 'my-deploy-config',
      engine: 'nim',
      model_spec: {
        model_namespace: workspace,
        model_name: 'my-deploy',
      },
      executor_config: {
        gpu: 2,
      },
      model_entity_id: 'ws/my-deploy',
    });

    expect(mockModelsCreateDeployment).toHaveBeenCalledWith(workspace, {
      name: 'my-deploy-deployment',
      config: 'my-deploy-config',
    });

    expect(onSuccess).toHaveBeenCalled();
  });

  it('surfaces submit errors and does not call onSuccess', async () => {
    mockModelsCreateDeploymentConfig.mockRejectedValueOnce(new Error('boom'));

    const { result } = renderHook(() => useCreateDeploymentBySource(workspace), { wrapper });
    const onSuccess = vi.fn();

    await act(async () => {
      await result.current.createDeploymentFromWizard(
        baseWorkspaceValues({
          workspacePickerType: WORKSPACE_PICKER_MODEL,
          modelRef: 'ws/m',
        }),
        onSuccess
      );
    });

    expect(onSuccess).not.toHaveBeenCalled();
    expect(result.current.submitError).toBeTruthy();
  });
});
