// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getPromptTuningFormRoute,
  getWorkspaceBaseModelsRoute,
  getWorkspaceInferenceProvidersRoute,
} from '@studio/routes/utils';

describe('getWorkspaceInferenceProvidersRoute', () => {
  const workspace = 'test-namespace/test-project';

  it('returns base inference providers path when no options are given', () => {
    expect(getWorkspaceInferenceProvidersRoute(workspace)).toBe(
      '/workspaces/test-namespace/test-project/inference-providers'
    );
  });

  it('appends create=true and preset query params when a preset is provided', () => {
    expect(getWorkspaceInferenceProvidersRoute(workspace, { preset: 'build' })).toBe(
      '/workspaces/test-namespace/test-project/inference-providers?create=true&preset=build'
    );
  });
});

describe('getWorkspaceBaseModelsRoute (deep linking)', () => {
  const workspace = 'my-workspace';

  it('returns base models list path when no options', () => {
    expect(getWorkspaceBaseModelsRoute(workspace)).toBe('/workspaces/my-workspace/base-models');
  });

  it('encodes model names with special characters (e.g. slash) for the path', () => {
    expect(getWorkspaceBaseModelsRoute(workspace, { model: 'org/my-model' })).toBe(
      '/workspaces/my-workspace/base-models/org%2Fmy-model'
    );
  });

  it('appends tab query param when both model and tab are provided', () => {
    expect(
      getWorkspaceBaseModelsRoute(workspace, {
        model: 'my-model',
        tab: 'chat-playground',
      })
    ).toBe('/workspaces/my-workspace/base-models/my-model?tab=chat-playground');
  });

  it('preserves provided query params on model detail paths', () => {
    const searchParams = new URLSearchParams({
      s: 'llama',
      filters: JSON.stringify([{ id: 'customizable', value: { fine_tunable: true } }]),
      sort: '-created_at',
    });

    expect(getWorkspaceBaseModelsRoute(workspace, { model: 'my-model', searchParams })).toBe(
      `/workspaces/my-workspace/base-models/my-model?${searchParams.toString()}`
    );
  });

  it('combines provided query params with tab query param', () => {
    const searchParams = new URLSearchParams({ s: 'llama' });

    expect(
      getWorkspaceBaseModelsRoute(workspace, {
        model: 'my-model',
        tab: 'chat-playground',
        searchParams,
      })
    ).toBe('/workspaces/my-workspace/base-models/my-model?s=llama&tab=chat-playground');
  });

  it('preserves provided query params on base models list paths', () => {
    const searchParams = new URLSearchParams({ s: 'llama', sort: '-created_at' });

    expect(getWorkspaceBaseModelsRoute(workspace, { searchParams })).toBe(
      '/workspaces/my-workspace/base-models?s=llama&sort=-created_at'
    );
  });
});

describe('getPromptTuningFormRoute', () => {
  const workspace = 'my-workspace';

  it('returns the bare prompt tuning form path when no model is given', () => {
    expect(getPromptTuningFormRoute(workspace)).toBe(
      '/workspaces/my-workspace/customizations/prompt-tuned/new'
    );
  });

  it('appends an encoded ?model= query param when a model URN is provided', () => {
    expect(getPromptTuningFormRoute(workspace, { model: 'my-workspace/my-model' })).toBe(
      '/workspaces/my-workspace/customizations/prompt-tuned/new?model=my-workspace%2Fmy-model'
    );
  });
});
