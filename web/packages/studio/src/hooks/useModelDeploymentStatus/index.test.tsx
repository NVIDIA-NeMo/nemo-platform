// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { useModelDeploymentStatus } from '@studio/hooks/useModelDeploymentStatus';
import { renderHook } from '@testing-library/react';

const mockGetProvider = vi.fn();
const mockGetLatestDeployment = vi.fn();

vi.mock('@nemo/sdk/generated/platform/model-providers', () => ({
  useModelsGetProvider: (...args: unknown[]) => mockGetProvider(...args),
}));

vi.mock('@nemo/sdk/generated/platform/model-deployments', () => ({
  useModelsGetLatestDeployment: (...args: unknown[]) => mockGetLatestDeployment(...args),
}));

const buildModel = (overrides: Partial<ModelEntity> = {}) =>
  ({ id: 'model-1', name: 'my-model', workspace: 'ws', ...overrides }) as ModelEntity;

beforeEach(() => {
  vi.clearAllMocks();
  mockGetProvider.mockReturnValue({ data: undefined, isLoading: false });
  mockGetLatestDeployment.mockReturnValue({ data: undefined, isLoading: false });
});

describe('useModelDeploymentStatus', () => {
  it('returns nulls when the model has no providers', () => {
    const { result } = renderHook(() => useModelDeploymentStatus(buildModel()));

    expect(result.current.status).toBeNull();
    expect(result.current.deployment).toBeNull();
    expect(result.current.deploymentRef).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('resolves the deployment through model_providers -> provider -> deployment', () => {
    mockGetProvider.mockReturnValue({
      data: { model_deployment_id: 'ws/my-deployment' },
      isLoading: false,
    });
    mockGetLatestDeployment.mockReturnValue({
      data: { name: 'my-deployment', workspace: 'ws', status: 'ready' },
      isLoading: false,
    });

    const { result } = renderHook(() =>
      useModelDeploymentStatus(buildModel({ model_providers: ['ws/my-provider'] }))
    );

    expect(result.current.status).toBe('ready');
    expect(result.current.deployment).toEqual({
      name: 'my-deployment',
      workspace: 'ws',
      status: 'ready',
    });
    expect(result.current.deploymentRef).toEqual({ workspace: 'ws', name: 'my-deployment' });
  });

  it('exposes deploymentRef before the deployment itself has loaded, so a link can render early', () => {
    mockGetProvider.mockReturnValue({
      data: { model_deployment_id: 'ws/my-deployment' },
      isLoading: false,
    });
    mockGetLatestDeployment.mockReturnValue({ data: undefined, isLoading: true });

    const { result } = renderHook(() =>
      useModelDeploymentStatus(buildModel({ model_providers: ['ws/my-provider'] }))
    );

    expect(result.current.deployment).toBeNull();
    expect(result.current.status).toBeNull();
    expect(result.current.deploymentRef).toEqual({ workspace: 'ws', name: 'my-deployment' });
    expect(result.current.isLoading).toBe(true);
  });

  it('keeps deploymentRef null when the provider names no deployment', () => {
    mockGetProvider.mockReturnValue({ data: { model_deployment_id: undefined }, isLoading: false });

    const { result } = renderHook(() =>
      useModelDeploymentStatus(buildModel({ model_providers: ['ws/my-provider'] }))
    );

    expect(result.current.deploymentRef).toBeNull();
    expect(result.current.deployment).toBeNull();
  });

  it('resolves a cross-workspace deployment reference to its own workspace', () => {
    mockGetProvider.mockReturnValue({
      data: { model_deployment_id: 'other-ws/shared-deployment' },
      isLoading: false,
    });
    mockGetLatestDeployment.mockReturnValue({
      data: { name: 'shared-deployment', workspace: 'other-ws', status: 'ready' },
      isLoading: false,
    });

    const { result } = renderHook(() =>
      useModelDeploymentStatus(buildModel({ model_providers: ['ws/my-provider'] }))
    );

    expect(result.current.deploymentRef).toEqual({
      workspace: 'other-ws',
      name: 'shared-deployment',
    });
  });
});
