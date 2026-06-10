// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  filesDeleteFileset,
  modelsDeleteAllDeploymentConfigVersions,
  modelsDeleteAllDeploymentVersions,
  modelsDeleteModel,
  modelsGetModel,
  modelsGetLatestDeployment,
  modelsGetLatestDeploymentConfig,
} from '@nemo/sdk/generated/platform/api';
import { ModelDeploymentStatus, type ModelDeployment } from '@nemo/sdk/generated/platform/schema';
import {
  HUGGING_FACE_DEPLOYMENT_SOURCE_FIELD,
  HUGGING_FACE_DEPLOYMENT_SOURCE_VALUE,
} from '@studio/routes/DeploymentsListRoute/huggingFaceDeploymentArtifacts';
import { useDeleteDeploymentAndConfig } from '@studio/routes/DeploymentsListRoute/useDeleteDeploymentAndConfig';
import { wrapper } from '@studio/tests/util/TestQueryClient';
import { act, renderHook } from '@testing-library/react';

vi.mock('@nemo/common/src/providers/toast/useToast');
vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return {
    ...actual,
    filesDeleteFileset: vi.fn(),
    modelsDeleteAllDeploymentConfigVersions: vi.fn(),
    modelsDeleteAllDeploymentVersions: vi.fn(),
    modelsDeleteModel: vi.fn(),
    modelsGetModel: vi.fn(),
    modelsGetLatestDeployment: vi.fn(),
    modelsGetLatestDeploymentConfig: vi.fn(),
  };
});

const mockUseToast = vi.mocked(useToast);
const mockFilesDeleteFileset = vi.mocked(filesDeleteFileset);
const mockModelsDeleteAllDeploymentConfigVersions = vi.mocked(
  modelsDeleteAllDeploymentConfigVersions
);
const mockModelsDeleteAllDeploymentVersions = vi.mocked(modelsDeleteAllDeploymentVersions);
const mockModelsDeleteModel = vi.mocked(modelsDeleteModel);
const mockModelsGetModel = vi.mocked(modelsGetModel);
const mockModelsGetLatestDeployment = vi.mocked(modelsGetLatestDeployment);
const mockModelsGetLatestDeploymentConfig = vi.mocked(modelsGetLatestDeploymentConfig);

const workspace = 'workspace';
const deployment: ModelDeployment = {
  name: 'deployment',
  workspace,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  entity_version: 1,
  config: 'deployment-config',
  config_version: 1,
  status: ModelDeploymentStatus.READY,
};

describe('useDeleteDeploymentAndConfig', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();

    mockUseToast.mockReturnValue({
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
      workingWithId: vi.fn(),
      dismissToast: vi.fn(),
    } as unknown as ReturnType<typeof useToast>);

    mockFilesDeleteFileset.mockResolvedValue(undefined as never);
    mockModelsDeleteAllDeploymentConfigVersions.mockResolvedValue(undefined as never);
    mockModelsDeleteAllDeploymentVersions.mockResolvedValue(undefined as never);
    mockModelsDeleteModel.mockResolvedValue(undefined as never);
    mockModelsGetModel.mockResolvedValue({ custom_fields: {} } as never);
    mockModelsGetLatestDeploymentConfig.mockResolvedValue({
      name: 'deployment-config',
      workspace,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      entity_version: 1,
      engine: 'nim',
      model_spec: {
        model_namespace: workspace,
        model_name: 'deployment-model',
      },
      executor_config: {
        gpu: 1,
      },
    } as never);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('resolves once the deployment reaches DELETING and cleans up config after DELETED', async () => {
    mockModelsGetLatestDeployment
      .mockResolvedValueOnce({
        ...deployment,
        status: ModelDeploymentStatus.DELETING,
      })
      .mockResolvedValueOnce({
        ...deployment,
        status: ModelDeploymentStatus.DELETING,
      })
      .mockResolvedValueOnce({
        ...deployment,
        status: ModelDeploymentStatus.DELETED,
      });

    const { result } = renderHook(() => useDeleteDeploymentAndConfig(workspace), { wrapper });

    await act(async () => {
      await result.current.deleteDeploymentAndConfig(deployment);
    });

    expect(mockModelsDeleteAllDeploymentVersions).toHaveBeenCalledWith(workspace, deployment.name);
    expect(mockModelsDeleteAllDeploymentConfigVersions).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(mockModelsDeleteAllDeploymentConfigVersions).toHaveBeenCalledWith(
      workspace,
      deployment.config
    );
  });

  it('cleans up Studio-created Hugging Face model and fileset after config deletion', async () => {
    mockModelsGetLatestDeployment
      .mockResolvedValueOnce({
        ...deployment,
        status: ModelDeploymentStatus.DELETING,
      })
      .mockResolvedValueOnce({
        ...deployment,
        status: ModelDeploymentStatus.DELETED,
      });
    mockModelsGetModel.mockResolvedValueOnce({
      custom_fields: {
        [HUGGING_FACE_DEPLOYMENT_SOURCE_FIELD]: HUGGING_FACE_DEPLOYMENT_SOURCE_VALUE,
      },
    } as never);

    const { result } = renderHook(() => useDeleteDeploymentAndConfig(workspace), { wrapper });

    await act(async () => {
      await result.current.deleteDeploymentAndConfig(deployment);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(mockModelsDeleteModel).toHaveBeenCalledWith(workspace, 'deployment-model');
    expect(mockFilesDeleteFileset).toHaveBeenCalledWith(workspace, 'deployment-hf-src');
  });

  it('does not plan Hugging Face cleanup when config only has model name', async () => {
    mockModelsGetLatestDeployment
      .mockResolvedValueOnce({
        ...deployment,
        status: ModelDeploymentStatus.DELETING,
      })
      .mockResolvedValueOnce({
        ...deployment,
        status: ModelDeploymentStatus.DELETED,
      });
    mockModelsGetLatestDeploymentConfig.mockResolvedValueOnce({
      name: 'deployment-config',
      workspace,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      entity_version: 1,
      engine: 'nim',
      model_spec: {
        model_name: 'deployment-model',
      },
      executor_config: {
        gpu: 1,
      },
    } as never);

    const { result } = renderHook(() => useDeleteDeploymentAndConfig(workspace), { wrapper });

    await act(async () => {
      await result.current.deleteDeploymentAndConfig(deployment);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(mockModelsDeleteAllDeploymentConfigVersions).toHaveBeenCalledWith(
      workspace,
      deployment.config
    );
    expect(mockModelsGetModel).not.toHaveBeenCalled();
    expect(mockModelsDeleteModel).not.toHaveBeenCalled();
    expect(mockFilesDeleteFileset).not.toHaveBeenCalled();
  });
});
