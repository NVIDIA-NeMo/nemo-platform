// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelDeploymentStatus, type ModelEntity } from '@nemo/sdk/generated/platform/schema';

import { getModelEntityChatStatus, groupModelsByWorkspace } from './models';

const createModel = (overrides: Partial<ModelEntity> = {}): ModelEntity => ({
  id: 'test-id',
  name: 'test-model',
  workspace: 'test-namespace',
  created_at: '2025-01-07T12:00:00Z',
  updated_at: '2025-01-07T12:00:00Z',
  ...overrides,
});

describe('getModelEntityChatStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns pending when model created less than 5 minutes ago', () => {
    const now = new Date('2025-01-07T12:00:00Z').getTime();
    vi.setSystemTime(now);

    const model = createModel({
      created_at: '2025-01-07T11:57:00Z', // 3 minutes ago
    });

    expect(getModelEntityChatStatus(model)).toBe('pending');
  });

  it('returns enabled when model created more than 5 minutes ago', () => {
    const now = new Date('2025-01-07T12:00:00Z').getTime();
    vi.setSystemTime(now);

    const model = createModel({
      created_at: '2025-01-07T11:50:00Z', // 10 minutes ago
    });

    expect(getModelEntityChatStatus(model)).toBe('enabled');
  });

  it('returns enabled when no created_at field', () => {
    const model = createModel();

    expect(getModelEntityChatStatus(model)).toBe('enabled');
  });

  it('handles created_at without timezone indicator (no Z suffix) as UTC', () => {
    const now = new Date('2025-01-07T12:00:00Z').getTime();
    vi.setSystemTime(now);

    const model = createModel({
      created_at: '2025-01-07T11:57:00', // No Z suffix, 3 minutes ago
    });

    expect(getModelEntityChatStatus(model)).toBe('pending');
  });

  it('handles created_at without timezone when model is old', () => {
    const now = new Date('2025-01-07T12:00:00Z').getTime();
    vi.setSystemTime(now);

    const model = createModel({
      created_at: '2025-01-07T11:50:00', // No Z suffix, 10 minutes ago
    });

    expect(getModelEntityChatStatus(model)).toBe('enabled');
  });

  it('handles created_at with +00:00 timezone offset', () => {
    const now = new Date('2025-01-07T12:00:00Z').getTime();
    vi.setSystemTime(now);

    // 11:57:00+00:00 is the same as 11:57:00Z (3 minutes ago)
    const model = createModel({
      created_at: '2025-01-07T11:57:00+00:00',
    });

    expect(getModelEntityChatStatus(model)).toBe('pending');
  });

  it('handles created_at with positive timezone offset', () => {
    const now = new Date('2025-01-07T12:00:00Z').getTime();
    vi.setSystemTime(now);

    // 17:27:00+05:30 is equivalent to 11:57:00 UTC (3 minutes ago)
    const model = createModel({
      created_at: '2025-01-07T17:27:00+05:30',
    });

    expect(getModelEntityChatStatus(model)).toBe('pending');
  });

  it('handles created_at with negative timezone offset', () => {
    const now = new Date('2025-01-07T12:00:00Z').getTime();
    vi.setSystemTime(now);

    // 06:57:00-05:00 is equivalent to 11:57:00 UTC (3 minutes ago)
    const model = createModel({
      created_at: '2025-01-07T06:57:00-05:00',
    });

    expect(getModelEntityChatStatus(model)).toBe('pending');
  });
});

describe('getModelEntityChatStatus (deployment & api_endpoint)', () => {
  const stableModel: ModelEntity = createModel({
    created_at: '2025-01-07T11:00:00Z',
    updated_at: '2025-01-07T11:00:00Z',
  });

  it('enables standalone models with api_endpoint.url', () => {
    expect(
      getModelEntityChatStatus({
        ...stableModel,
        api_endpoint: { url: 'https://example/v1/chat/completions' },
      } as ModelEntity)
    ).toBe('enabled');
  });

  it('disables standalone models without api_endpoint when deployment is null', () => {
    expect(getModelEntityChatStatus(stableModel, { deploymentStatus: null })).toBe('disabled');
  });

  it('enables standalone models with READY deployment and no api_endpoint', () => {
    expect(
      getModelEntityChatStatus(stableModel, { deploymentStatus: ModelDeploymentStatus.READY })
    ).toBe('enabled');
  });

  it('requires READY deployment for base_model when status is provided', () => {
    const derived = { ...stableModel, base_model: 'ws/parent' } as ModelEntity;
    expect(
      getModelEntityChatStatus(derived, { deploymentStatus: ModelDeploymentStatus.READY })
    ).toBe('enabled');
    expect(
      getModelEntityChatStatus(derived, { deploymentStatus: ModelDeploymentStatus.ERROR })
    ).toBe('disabled');
    expect(getModelEntityChatStatus(derived)).toBe('enabled');
  });

  it('returns pending while deployment is loading', () => {
    expect(getModelEntityChatStatus(stableModel, { deploymentLoading: true })).toBe('pending');
  });
});

describe('groupModelsByWorkspace', () => {
  it('returns [] for an empty list', () => {
    expect(groupModelsByWorkspace([])).toEqual([]);
  });

  it('groups models by workspace and preserves model order within each group', () => {
    const m1 = createModel({ id: 'm1', name: 'a', workspace: 'nvidia' });
    const m2 = createModel({ id: 'm2', name: 'b', workspace: 'meta' });
    const m3 = createModel({ id: 'm3', name: 'c', workspace: 'nvidia' });
    const groups = groupModelsByWorkspace([m1, m2, m3]);

    expect(groups).toHaveLength(2);
    const nvidia = groups.find((g) => g.workspace === 'nvidia');
    const meta = groups.find((g) => g.workspace === 'meta');
    expect(nvidia?.models).toEqual([m1, m3]);
    expect(meta?.models).toEqual([m2]);
  });

  it("falls back to 'default' when workspace is missing", () => {
    const m = {
      ...createModel({ name: 'a' }),
      workspace: undefined,
    } as unknown as ModelEntity;
    const [group] = groupModelsByWorkspace([m]);
    expect(group.workspace).toBe('default');
    expect(group.models).toEqual([m]);
  });

  it('sorts groups alphabetically by workspace name when sort is true', () => {
    const groups = groupModelsByWorkspace(
      [
        createModel({ id: 'm1', name: 'a', workspace: 'nvidia' }),
        createModel({ id: 'm2', name: 'b', workspace: 'meta' }),
        createModel({ id: 'm3', name: 'c', workspace: 'deepseek' }),
      ],
      { sort: true }
    );
    expect(groups.map((g) => g.workspace)).toEqual(['deepseek', 'meta', 'nvidia']);
  });
});
