// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
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

const makeGroups = (models: ModelEntity[]): ModelWorkspaceGroup[] => {
  const byWorkspace = new Map<string, ModelEntity[]>();
  for (const m of models) {
    const ws = m.workspace ?? '';
    if (!byWorkspace.has(ws)) byWorkspace.set(ws, []);
    byWorkspace.get(ws)!.push(m);
  }
  return Array.from(byWorkspace.entries()).map(([workspace, models]) => ({ workspace, models }));
};

const renderPanel = (modelURN: string | null, modelGroups: ModelWorkspaceGroup[]) => {
  return render(
    <TestProviders>
      <MemoryRouter>
        <ModelChatPanel
          panel={{
            id: 0,
            collapsed: false,
            modelURN,
            roleColor: 'baseline',
            roleLabel: 'Baseline',
            isSinglePanel: true,
            locked: false,
          }}
          fallbackWorkspace="route-workspace"
          modelGroups={modelGroups}
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
    renderPanel(
      'nvidia/llama-70b',
      makeGroups([makeModel('abacusai', 'llama-70b'), makeModel('nvidia', 'llama-70b')])
    );

    expect(modelChatSpy).toHaveBeenCalledWith(
      expect.objectContaining({ workspace: 'nvidia', model: 'llama-70b' })
    );
  });

  it('picks the correct workspace even when two models share the same name', () => {
    // The previous name-based lookup would have silently bound this panel to
    // whichever workspace's model came first in the list. With URNs end-to-end,
    // the workspace selected in the URN is used.
    renderPanel(
      'abacusai/llama-70b',
      makeGroups([makeModel('nvidia', 'llama-70b'), makeModel('abacusai', 'llama-70b')])
    );

    expect(modelChatSpy).toHaveBeenCalledWith(
      expect.objectContaining({ workspace: 'abacusai', model: 'llama-70b' })
    );
  });

  it('falls back to the route workspace and disables chat when no model is assigned', () => {
    renderPanel(null, []);
    // ModelChat still renders, but disabled and showing an empty state; with no
    // model URN it uses the route fallback workspace and an empty model id.
    expect(modelChatSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        workspace: 'route-workspace',
        model: '',
        disabled: true,
        emptyState: expect.objectContaining({ slotHeading: expect.any(String) }),
      })
    );
  });
});
