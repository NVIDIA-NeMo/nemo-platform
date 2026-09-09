// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { DeployModelButton } from '@studio/components/DeployModelButton';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';

const mockNavigate = vi.fn();
const mockDeploymentStatus = vi.fn();
const mockEnvironment = vi.hoisted(() => ({ deploymentsEnabled: true }));

vi.mock('@studio/constants/environment', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@studio/constants/environment')>();
  return {
    ...actual,
    get DEPLOYMENTS_ENABLED() {
      return mockEnvironment.deploymentsEnabled;
    },
  };
});

vi.mock('@studio/hooks/useModelDeploymentStatus', () => ({
  useModelDeploymentStatus: (...args: unknown[]) => mockDeploymentStatus(...args),
}));

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...(actual as object), useNavigate: () => mockNavigate };
});

const buildModel = (overrides: Partial<ModelEntity> = {}) =>
  ({
    id: 'model-1',
    name: 'my-model',
    workspace: 'ws',
    fileset: 'ws/my-fs',
    ...overrides,
  }) as ModelEntity;

const renderButton = (model?: ModelEntity) =>
  render(
    <MemoryRouter>
      <DeployModelButton workspace="ws" model={model} />
    </MemoryRouter>
  );

beforeEach(() => {
  vi.clearAllMocks();
  mockEnvironment.deploymentsEnabled = true;
  mockDeploymentStatus.mockReturnValue({ deploymentRef: null, isLoading: false });
});

describe('DeployModelButton', () => {
  it('offers Deploy for a deployable, undeployed model', () => {
    renderButton(buildModel());
    expect(screen.getByRole('button', { name: /Deploy/ })).toBeInTheDocument();
  });

  it('deep links to the create-deployment wizard prefilled with the model', async () => {
    const user = userEvent.setup();
    renderButton(buildModel());

    await user.click(screen.getByRole('button', { name: /Deploy/ }));

    expect(mockNavigate).toHaveBeenCalledWith('/workspaces/ws/deployments?model=ws%2Fmy-model');
  });

  it('renders nothing when deployments are disabled, so the CTA cannot link into a 404', () => {
    mockEnvironment.deploymentsEnabled = false;
    const { container } = renderButton(buildModel());
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for a model with no fileset, which the wizard cannot deploy', () => {
    const { container } = renderButton(buildModel({ fileset: undefined }));
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing without a model', () => {
    const { container } = renderButton(undefined);
    expect(container).toBeEmptyDOMElement();
  });

  it('links to the existing deployment instead of offering to create another', async () => {
    const user = userEvent.setup();
    mockDeploymentStatus.mockReturnValue({
      deploymentRef: { workspace: 'ws', name: 'my-deployment' },
      isLoading: false,
    });

    renderButton(buildModel());

    expect(screen.queryByRole('button', { name: /^Deploy$/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /View Deployment/ }));

    expect(mockNavigate).toHaveBeenCalledWith('/workspaces/ws/deployments/my-deployment/details');
  });

  it('follows a cross-workspace deployment to its own workspace', async () => {
    const user = userEvent.setup();
    mockDeploymentStatus.mockReturnValue({
      deploymentRef: { workspace: 'other-ws', name: 'shared' },
      isLoading: false,
    });

    renderButton(buildModel());
    await user.click(screen.getByRole('button', { name: /View Deployment/ }));

    expect(mockNavigate).toHaveBeenCalledWith('/workspaces/other-ws/deployments/shared/details');
  });
});
