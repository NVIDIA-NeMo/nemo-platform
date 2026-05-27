// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ChatCompletionToolsParam } from '@nemo/common/src/zod/tools';
import { ToolMetadataPanel } from '@studio/components/PromptTuningForm/ToolsSection/components/ToolMetadataPanel';
import { mockTool } from '@studio/mocks/studio-ui/tool';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

// Mock the CodeEditor component
vi.mock('@nemo/common/src/components/CodeEditor', () => ({
  CodeEditor: ({ content, title }: { content: string; title: string }) => (
    <div data-testid="code-editor" data-content={content} data-title={title}>
      Code Editor: {title}
    </div>
  ),
}));

describe('ToolMetadataModal', () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders nothing when tool is not provided', () => {
      render(<ToolMetadataPanel open onClose={mockOnClose} />);
      expect(screen.queryByText('Tool Metadata')).not.toBeInTheDocument();
    });

    it('renders modal with tool information when tool is provided', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      expect(screen.getByText('Tool Metadata')).toBeInTheDocument();
      expect(screen.getByText('test_function')).toBeInTheDocument();
      expect(screen.getByText('A test function for testing purposes')).toBeInTheDocument();
    });

    it('renders basic information section', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      expect(screen.getByText('Basic Information')).toBeInTheDocument();
      expect(screen.getByText('Function Name')).toBeInTheDocument();
      expect(screen.getByText('Description')).toBeInTheDocument();
    });

    it('renders parameters section', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      expect(screen.getByText('Parameters')).toBeInTheDocument();
      expect(screen.getByText('param1')).toBeInTheDocument();
      expect(screen.getByText('param2')).toBeInTheDocument();
    });

    it('renders CodeEditor with tool definition', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      const codeEditor = screen.getByTestId('code-editor');
      expect(codeEditor).toBeInTheDocument();
      expect(codeEditor).toHaveAttribute('data-content', JSON.stringify(mockTool, null, 2));
    });
  });

  describe('parameter details', () => {
    it('displays parameter types correctly', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      expect(screen.getByText('Type: string')).toBeInTheDocument();
      expect(screen.getByText('Type: number')).toBeInTheDocument();
    });

    it('displays parameter descriptions when available', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      expect(screen.getByText('First parameter')).toBeInTheDocument();
      expect(screen.getByText('Second parameter')).toBeInTheDocument();
    });

    it('shows required indicator for required parameters', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      const requiredIndicators = screen.getAllByText('(Required)');
      expect(requiredIndicators).toHaveLength(1);
    });

    it('handles tool without parameters', () => {
      const toolWithoutParams = {
        ...mockTool,
        function: {
          ...mockTool.function,
          parameters: undefined,
        },
      };

      render(<ToolMetadataPanel open tool={toolWithoutParams} onClose={mockOnClose} />);

      expect(screen.getByText('No parameters defined')).toBeInTheDocument();
    });

    it('handles tool with empty parameters object', () => {
      const toolWithEmptyParams = {
        ...mockTool,
        function: {
          ...mockTool.function,
          parameters: {
            type: 'object',
            properties: {},
            required: [],
          },
        },
      };

      render(<ToolMetadataPanel open tool={toolWithEmptyParams} onClose={mockOnClose} />);

      expect(screen.getByText('No parameters defined')).toBeInTheDocument();
    });
  });

  describe('modal behavior', () => {
    it('calls onClose when modal is closed', async () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      // KUI SidePanel uses a native <dialog> with a hidden form[method="dialog"].
      // happy-dom does not fire the dialog close event when that form submits,
      // so simulate the native close event directly.
      const dialog = screen.getByRole('dialog', { hidden: true });
      fireEvent(dialog, new Event('close'));
      await waitFor(() => expect(mockOnClose).toHaveBeenCalled());
    });

    it('renders with correct modal structure', () => {
      render(<ToolMetadataPanel open tool={mockTool} onClose={mockOnClose} />);

      expect(screen.getByText('Tool Metadata')).toBeInTheDocument();
      expect(screen.getByTestId('code-editor')).toBeInTheDocument();
    });
  });

  describe('edge cases', () => {
    it('handles tool with complex parameter types', () => {
      const complexTool: ChatCompletionToolsParam = {
        type: 'function',
        function: {
          name: 'complex_function',
          description: 'A complex function',
          parameters: {
            type: 'object',
            properties: {
              arrayParam: {
                type: 'array',
                description: 'An array parameter',
              },
              objectParam: {
                type: 'object',
                description: 'An object parameter',
              },
            },
            required: ['arrayParam'],
          },
        },
      };

      render(<ToolMetadataPanel open tool={complexTool} onClose={mockOnClose} />);

      expect(screen.getByText('Type: array')).toBeInTheDocument();
      expect(screen.getByText('Type: object')).toBeInTheDocument();
      expect(screen.getByText('An array parameter')).toBeInTheDocument();
      expect(screen.getByText('An object parameter')).toBeInTheDocument();
    });

    it('handles tool with no required parameters', () => {
      const toolWithNoRequired = {
        ...mockTool,
        function: {
          ...mockTool.function,
          parameters: {
            ...mockTool.function.parameters!,
            required: [],
          },
        },
      };

      render(<ToolMetadataPanel open tool={toolWithNoRequired} onClose={mockOnClose} />);

      expect(screen.queryByText('(Required)')).not.toBeInTheDocument();
    });
  });
});
