// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAuthTokenStatus } from '@studio/providers/auth/useAuthTokenStatus';
import { WorkspaceGuard } from '@studio/routes/RootLayout/WorkspaceGuard';
import { MockWorkspaceProvider } from '@studio/tests/mocks/MockWorkspaceProvider';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@studio/providers/auth/useAuthTokenStatus', () => ({
  useAuthTokenStatus: vi.fn(),
}));

const mockUseAuthTokenStatus = vi.mocked(useAuthTokenStatus);

const renderGuard = ({
  isTokenActive = true,
  isWorkspaceUnauthorized = false,
  isWorkspaceLoading = false,
  workspace = 'test-workspace' as string | undefined,
} = {}) => {
  mockUseAuthTokenStatus.mockReturnValue({
    isTokenActive,
    isAuthenticated: isTokenActive,
    isLoading: false,
    isExpired: false,
    activeScopes: [],
    expiresAt: undefined,
  });

  return render(
    <TestProviders>
      <MemoryRouter>
        <MockWorkspaceProvider
          defaultWorkspace={workspace}
          isWorkspaceUnauthorized={isWorkspaceUnauthorized}
          isWorkspaceLoading={isWorkspaceLoading}
        >
          <WorkspaceGuard>
            <div>protected content</div>
          </WorkspaceGuard>
        </MockWorkspaceProvider>
      </MemoryRouter>
    </TestProviders>
  );
};

describe('WorkspaceGuard', () => {
  it('renders children when token is active and workspace is authorized', () => {
    renderGuard();
    expect(screen.getByText('protected content')).toBeInTheDocument();
  });

  it('renders children when token is not active', () => {
    renderGuard({ isTokenActive: false });
    expect(screen.getByText('protected content')).toBeInTheDocument();
  });

  it('renders children when no workspace is selected', () => {
    renderGuard({ workspace: undefined });
    expect(screen.getByText('protected content')).toBeInTheDocument();
  });

  it('renders loading state while workspace check is in progress', () => {
    renderGuard({ isWorkspaceLoading: true });
    expect(screen.getByText('Checking workspace access...')).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('renders unauthorized screen when workspace access is denied', () => {
    renderGuard({ isWorkspaceUnauthorized: true });
    expect(screen.getByText("You don't have access to this workspace")).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });
});
