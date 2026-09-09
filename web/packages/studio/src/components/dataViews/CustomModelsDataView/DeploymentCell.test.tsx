// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DeploymentCell } from '@studio/components/dataViews/CustomModelsDataView/DeploymentCell';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

const mockGetModel = vi.fn();
const mockDeploymentStatus = vi.fn();

vi.mock('@nemo/sdk/generated/platform/models', () => ({
  useModelsGetModel: (...args: unknown[]) => mockGetModel(...args),
}));

vi.mock('@studio/hooks/useModelDeploymentStatus', () => ({
  useModelDeploymentStatus: (...args: unknown[]) => mockDeploymentStatus(...args),
}));

const renderCell = (props: { providerIds?: string[]; baseModel?: string } = {}) =>
  render(
    <MemoryRouter>
      <DeploymentCell
        workspace="ws"
        providerIds={props.providerIds}
        baseModel={props.baseModel ?? 'base-model'}
      />
    </MemoryRouter>
  );

beforeEach(() => {
  vi.clearAllMocks();
  mockGetModel.mockReturnValue({
    data: { name: 'base-model', workspace: 'ws' },
    isLoading: false,
  });
  mockDeploymentStatus.mockReturnValue({
    status: null,
    deploymentRef: null,
    isLoading: false,
  });
});

describe('DeploymentCell', () => {
  it('names the deployment and links to its details route', () => {
    mockDeploymentStatus.mockReturnValue({
      status: 'ready',
      deploymentRef: { workspace: 'ws', name: 'my-deployment' },
      isLoading: false,
    });

    renderCell({ providerIds: ['ws/provider-1'] });

    const link = screen.getByRole('link', { name: 'my-deployment' });
    expect(link).toHaveAttribute('href', '/workspaces/ws/deployments/my-deployment/details');
  });

  it('renders an explicit empty state rather than a blank cell when undeployed', () => {
    renderCell();
    expect(screen.getByText('Not deployed')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('grafts the row own providers onto the base model entity before resolving', () => {
    renderCell({ providerIds: ['ws/provider-1'] });

    expect(mockDeploymentStatus).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'base-model', model_providers: ['ws/provider-1'] })
    );
  });

  it('counts the remaining deployments when several providers serve the model', () => {
    mockDeploymentStatus.mockReturnValue({
      status: 'ready',
      deploymentRef: { workspace: 'ws', name: 'first-deployment' },
      isLoading: false,
    });

    renderCell({ providerIds: ['ws/p1', 'ws/p2', 'ws/p3'] });

    expect(screen.getByRole('link', { name: 'first-deployment' })).toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
  });

  it('does not count extras when a single provider serves the model', () => {
    mockDeploymentStatus.mockReturnValue({
      status: 'ready',
      deploymentRef: { workspace: 'ws', name: 'only-deployment' },
      isLoading: false,
    });

    renderCell({ providerIds: ['ws/p1'] });

    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
  });

  it('links across workspaces when the deployment lives elsewhere', () => {
    mockDeploymentStatus.mockReturnValue({
      status: 'ready',
      deploymentRef: { workspace: 'other-ws', name: 'shared' },
      isLoading: false,
    });

    renderCell({ providerIds: ['ws/p1'] });

    expect(screen.getByRole('link', { name: 'shared' })).toHaveAttribute(
      'href',
      '/workspaces/other-ws/deployments/shared/details'
    );
  });

  it('shows a skeleton while the base model is still resolving', () => {
    mockGetModel.mockReturnValue({ data: undefined, isLoading: true });
    renderCell();

    // Must not claim "Not deployed" before the walk has finished, or every row
    // would flash an incorrect empty state on first paint.
    expect(screen.queryByText('Not deployed')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Loading deployment')).toBeInTheDocument();
  });
});
