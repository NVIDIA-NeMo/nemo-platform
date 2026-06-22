// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ThemeProvider } from '@nvidia/foundations-react-core';
import { SafeSynthesizerNavigation } from '@studio/components/SafeSynthesizerNavigation';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useNavigate } from 'react-router-dom';

// Mock the hooks
vi.mock('@studio/hooks/useWorkspaceFromPath');
vi.mock('react-router-dom');

const mockNavigate = vi.fn();
const mockuseWorkspaceFromPath = vi.mocked(useWorkspaceFromPath);
const mockUseNavigate = vi.mocked(useNavigate);

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <ThemeProvider density="standard" theme="light">
    {children}
  </ThemeProvider>
);

describe('SafeSynthesizerNavigation', () => {
  const testJobId = 'test-job-123';
  const testWorkspace = 'test-workspace';

  beforeEach(() => {
    vi.clearAllMocks();

    mockuseWorkspaceFromPath.mockReturnValue(testWorkspace);

    mockUseNavigate.mockReturnValue(mockNavigate);
  });

  describe('Visual Rendering', () => {
    it('should render the page heading', () => {
      render(<SafeSynthesizerNavigation selected="summary" jobName={testJobId} />, {
        wrapper: Wrapper,
      });

      expect(screen.getByTestId('nv-page-header-heading')).toHaveTextContent(
        'Safe Synthesizer Job'
      );
    });

    it('should render Summary and Report tabs', () => {
      render(<SafeSynthesizerNavigation selected="summary" jobName={testJobId} />, {
        wrapper: Wrapper,
      });

      expect(screen.getByRole('tab', { name: 'Summary' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Report' })).toBeInTheDocument();
    });

    it('should show summary tab as selected when selected="summary"', () => {
      render(<SafeSynthesizerNavigation selected="summary" jobName={testJobId} />, {
        wrapper: Wrapper,
      });

      const summaryTab = screen.getByRole('tab', { name: 'Summary' });
      const reportTab = screen.getByRole('tab', { name: 'Report' });

      expect(summaryTab).toHaveAttribute('aria-selected', 'true');
      expect(reportTab).toHaveAttribute('aria-selected', 'false');
    });

    it('should show report tab as selected when selected="report"', () => {
      render(<SafeSynthesizerNavigation selected="report" jobName={testJobId} />, {
        wrapper: Wrapper,
      });

      const summaryTab = screen.getByRole('tab', { name: 'Summary' });
      const reportTab = screen.getByRole('tab', { name: 'Report' });

      expect(summaryTab).toHaveAttribute('aria-selected', 'false');
      expect(reportTab).toHaveAttribute('aria-selected', 'true');
    });
  });

  describe('Navigation', () => {
    it('should navigate to job details when summary tab is clicked', async () => {
      const user = userEvent.setup();
      render(<SafeSynthesizerNavigation selected="report" jobName={testJobId} />, {
        wrapper: Wrapper,
      });

      const summaryTab = screen.getByRole('tab', { name: 'Summary' });
      await user.click(summaryTab);

      expect(mockNavigate).toHaveBeenCalledWith(
        `/workspaces/${testWorkspace}/safe-synthesizer/job/${testJobId}`
      );
    });

    it('should navigate to job report when report tab is clicked', async () => {
      const user = userEvent.setup();
      render(<SafeSynthesizerNavigation selected="summary" jobName={testJobId} />, {
        wrapper: Wrapper,
      });

      const reportTab = screen.getByRole('tab', { name: 'Report' });
      await user.click(reportTab);

      expect(mockNavigate).toHaveBeenCalledWith(
        `/workspaces/${testWorkspace}/safe-synthesizer/job/${testJobId}/report`
      );
    });

    it('should use workspace from path context', async () => {
      const user = userEvent.setup();
      const customWorkspace = 'custom-workspace';
      mockuseWorkspaceFromPath.mockReturnValue(customWorkspace);

      render(<SafeSynthesizerNavigation selected="summary" jobName={testJobId} />, {
        wrapper: Wrapper,
      });

      const reportTab = screen.getByRole('tab', { name: 'Report' });
      await user.click(reportTab);

      expect(mockNavigate).toHaveBeenCalledWith(
        `/workspaces/${customWorkspace}/safe-synthesizer/job/${testJobId}/report`
      );
    });

    it('should use the provided jobId in navigation', async () => {
      const user = userEvent.setup();
      const customJobId = 'custom-job-456';

      render(<SafeSynthesizerNavigation selected="summary" jobName={customJobId} />, {
        wrapper: Wrapper,
      });

      const reportTab = screen.getByRole('tab', { name: 'Report' });
      await user.click(reportTab);

      expect(mockNavigate).toHaveBeenCalledWith(
        `/workspaces/${testWorkspace}/safe-synthesizer/job/${customJobId}/report`
      );
    });
  });
});
