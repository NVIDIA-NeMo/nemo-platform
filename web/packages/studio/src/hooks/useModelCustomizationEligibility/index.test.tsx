// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { useModelChatAvailability } from '@studio/hooks/useModelChatAvailability';
import { useModelCustomizationEligibility } from '@studio/hooks/useModelCustomizationEligibility';
import { useModelLoraEnabled } from '@studio/hooks/useModelLoraEnabled';
import { renderHook } from '@testing-library/react';

vi.mock('@studio/hooks/useModelChatAvailability', () => ({
  useModelChatAvailability: vi.fn(),
}));
vi.mock('@studio/hooks/useModelLoraEnabled', () => ({
  useModelLoraEnabled: vi.fn(),
}));

const mockedUseChatAvailability = vi.mocked(useModelChatAvailability);
const mockedUseLoraEnabled = vi.mocked(useModelLoraEnabled);

const setup = (
  overrides: {
    isChatAvailable?: boolean;
    isLoraEnabled?: boolean;
    isChatLoading?: boolean;
    isLoraLoading?: boolean;
  } = {}
) => {
  const isChatAvailable = overrides.isChatAvailable ?? true;
  mockedUseChatAvailability.mockReturnValue({
    isChatAvailable,
    modelChatStatus: isChatAvailable ? 'enabled' : 'disabled',
    isLoading: overrides.isChatLoading ?? false,
  });
  mockedUseLoraEnabled.mockReturnValue({
    isLoraEnabled: overrides.isLoraEnabled ?? false,
    isLoading: overrides.isLoraLoading ?? false,
  });
};

const buildModel = (overrides: Partial<ModelEntity> = {}): ModelEntity =>
  ({
    id: 'model-1',
    name: 'my-model',
    workspace: 'ws',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    ...overrides,
  }) as ModelEntity;

describe('useModelCustomizationEligibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setup();
  });

  it('canFineTune=true when model has a fileset', () => {
    const { result } = renderHook(() =>
      useModelCustomizationEligibility(buildModel({ fileset: 'ws/my-fs' }))
    );
    expect(result.current.canFineTune).toBe(true);
  });

  it('canFineTune=false when model has no fileset', () => {
    const { result } = renderHook(() => useModelCustomizationEligibility(buildModel()));
    expect(result.current.canFineTune).toBe(false);
  });

  it('canPromptTune=true when chat-available and lora is enabled', () => {
    setup({ isChatAvailable: true, isLoraEnabled: true });
    const { result } = renderHook(() => useModelCustomizationEligibility(buildModel()));
    expect(result.current.canPromptTune).toBe(true);
  });

  it('canPromptTune=false when lora is not enabled', () => {
    setup({ isChatAvailable: true, isLoraEnabled: false });
    const { result } = renderHook(() => useModelCustomizationEligibility(buildModel()));
    expect(result.current.canPromptTune).toBe(false);
  });

  it('canPromptTune=false when not chat-available, even with lora enabled', () => {
    setup({ isChatAvailable: false, isLoraEnabled: true });
    const { result } = renderHook(() => useModelCustomizationEligibility(buildModel()));
    expect(result.current.canPromptTune).toBe(false);
  });

  it('isLoading is true while chat availability is loading', () => {
    setup({ isChatLoading: true });
    const { result } = renderHook(() => useModelCustomizationEligibility(buildModel()));
    expect(result.current.isLoading).toBe(true);
  });

  it('isLoading is true while lora-enabled is loading', () => {
    setup({ isLoraLoading: true });
    const { result } = renderHook(() => useModelCustomizationEligibility(buildModel()));
    expect(result.current.isLoading).toBe(true);
  });
});
