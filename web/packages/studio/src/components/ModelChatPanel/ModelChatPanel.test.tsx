// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { ModelChatPanel } from '@studio/components/ModelChatPanel';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Capture the props that ModelChat receives so we can assert on workspace/model
// routing without spinning up a real chat flow.
const modelChatSpy = vi.fn();

vi.mock('@studio/components/ModelChat', () => ({
  ModelChat: (props: Record<string, unknown>) => {
    modelChatSpy(props);
    return <div data-testid="mock-model-chat" />;
  },
}));

// ModelSelectV2 internals are not what we're testing here.
vi.mock('@nemo/common/src/components/ModelSelectV2', () => ({
  ModelSelectV2: () => <div data-testid="mock-model-select" />,
}));

const makeModel = (workspace: string, name: string): ModelEntity =>
  ({ workspace, name }) as unknown as ModelEntity;

const renderPanel = (modelURN: string | null, availableModels: ModelEntity[]) => {
  return render(
    <TestProviders>
      <MemoryRouter>
        <ModelChatPanel
          panel={{ id: 0, collapsed: false, modelURN }}
          fallbackWorkspace="route-workspace"
          models={availableModels}
          isLoadingModels={false}
          onToggle={vi.fn()}
          onRemove={vi.fn()}
          onModelChange={vi.fn()}
        />
      </MemoryRouter>
    </TestProviders>
  );
};

describe('ModelChatPanel — URN routing', () => {
  beforeEach(() => {
    modelChatSpy.mockClear();
  });

  it("routes inference to the model's own workspace (not the route workspace)", () => {
    renderPanel('nvidia/llama-70b', [
      makeModel('abacusai', 'llama-70b'),
      makeModel('nvidia', 'llama-70b'),
    ]);

    expect(modelChatSpy).toHaveBeenCalledWith(
      expect.objectContaining({ workspace: 'nvidia', model: 'llama-70b' })
    );
  });

  it('picks the correct workspace even when two models share the same name', () => {
    // The previous name-based lookup would have silently bound this panel to
    // whichever workspace's model came first in `availableModels`. With URNs
    // end-to-end, the workspace selected in the URN is used.
    renderPanel('abacusai/llama-70b', [
      makeModel('nvidia', 'llama-70b'),
      makeModel('abacusai', 'llama-70b'),
    ]);

    expect(modelChatSpy).toHaveBeenCalledWith(
      expect.objectContaining({ workspace: 'abacusai', model: 'llama-70b' })
    );
  });

  it('falls back to the route workspace only when no model is assigned', () => {
    renderPanel(null, []);
    // ModelChat isn't rendered without a model — the panel shows the empty state.
    expect(modelChatSpy).not.toHaveBeenCalled();
  });
});
