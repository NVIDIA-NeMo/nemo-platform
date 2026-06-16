// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FilesetFilePreviewPanel } from '@studio/components/FilesetFilePreviewPanel';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, fireEvent } from '@testing-library/react';

// Mock the useWorkers hook since FileActions uses it
vi.mock('@studio/providers/workers/useWorkers', () => ({
  useWorkers: () => ({
    createWorker: vi.fn(),
  }),
}));

vi.mock('@studio/components/filesets/hooks/useIsBinaryFile', () => ({
  useIsBinaryFile: () => ({ isBinary: false, isLoading: false }),
}));

describe('FilesetFilePreviewPanel', () => {
  const defaultProps = {
    open: true,
    onCloseClick: vi.fn(),
    onOutsideClick: vi.fn(),
    workspace: 'default',
    filesetName: 'test-dataset',
    filePath: 'test.txt',
  };

  it('renders FilesetFilePreviewPanel', () => {
    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...defaultProps} />
      </TestProviders>
    );
    // Verify component renders by checking for auto-generated breadcrumbs
    expect(screen.getByText('test-dataset')).toBeInTheDocument();
    expect(screen.getByText('test.txt')).toBeInTheDocument();
  });

  it('renders JSON files with CodeEditor', async () => {
    const props = {
      ...defaultProps,
      filePath: 'data.json',
      fileContent: '{"key": "value"}',
      isLoading: false,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // CodeEditor should be rendered
    const codeEditor = await screen.findByTestId('nv-code-editor-root');
    expect(codeEditor).toBeInTheDocument();
  });

  it('renders text files with CodeEditor', async () => {
    const textContent = 'Line 1\nLine 2\nLine 3';
    const props = {
      ...defaultProps,
      filePath: 'data.txt',
      fileContent: textContent,
      isLoading: false,
      file: {
        type: 'file' as const,
        path: 'data.txt',
        size: 100,
        oid: 'mock-oid',
      },
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // CodeEditor should be rendered for text files
    const codeEditor = await screen.findByTestId('nv-code-editor-root');
    expect(codeEditor).toBeInTheDocument();
  });

  it('displays loading state', () => {
    const props = {
      ...defaultProps,
      isLoading: true,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );
    // Loading UI comes from FileContentPreview (spinner with aria-label="Loading...").
    expect(screen.getByLabelText('Loading...')).toBeInTheDocument();
  });

  it('displays error state', () => {
    const props = {
      ...defaultProps,
      error: new Error('Failed to load file'),
      isLoading: false,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );
    expect(screen.getByText('Error: Failed to load file')).toBeInTheDocument();
  });

  it('accepts pre-fetched data', () => {
    const props = {
      ...defaultProps,
      fileContent: 'Pre-fetched content',
      isLoading: false,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );
    expect(screen.getByText('Pre-fetched content')).toBeInTheDocument();
  });

  it('renders content with CodeEditor', async () => {
    const contentWithSpaces = '  Line with  multiple   spaces  ';
    const props = {
      ...defaultProps,
      fileContent: contentWithSpaces,
      isLoading: false,
      file: {
        type: 'file' as const,
        path: 'test.txt',
        size: 100,
        oid: 'mock-oid',
      },
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // CodeEditor should be rendered and preserve content
    const codeEditor = await screen.findByTestId('nv-code-editor-root');
    expect(codeEditor).toBeInTheDocument();
  });

  it('fetches data internally when not provided', async () => {
    const testFilePath = 'test-data.json';

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...defaultProps} filePath={testFilePath} />
      </TestProviders>
    );

    // Wait for the data to be fetched and rendered with CodeEditor
    const codeEditor = await screen.findByTestId('nv-code-editor-root');
    expect(codeEditor).toBeInTheDocument();
  });

  it('does not fetch data when pre-fetched data provided', () => {
    // Don't set up any handlers - if the component makes network requests, MSW will throw an error
    const props = {
      ...defaultProps,
      fileContent: 'Pre-fetched content',
      file: {
        type: 'file' as const,
        path: 'test.txt',
        size: 100,
        oid: 'mock-oid',
      },
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // Verify pre-fetched content is displayed without making network requests
    expect(screen.getByText('Pre-fetched content')).toBeInTheDocument();
  });

  it('renders JSONL files with CodeEditor', async () => {
    const props = {
      ...defaultProps,
      filePath: 'data.jsonl',
      fileContent: '{"line": 1}\n{"line": 2}',
      isLoading: false,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // JSONL content should be rendered with CodeEditor
    const codeEditor = await screen.findByTestId('nv-code-editor-root');
    expect(codeEditor).toBeInTheDocument();
  });

  it('calls onFolderClick when folder breadcrumb is clicked', () => {
    const onFolderClick = vi.fn();
    const props = {
      ...defaultProps,
      filePath: 'folder1/folder2/file.txt',
      onFolderClick,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // Click on the first folder breadcrumb
    const folder1Breadcrumb = screen.getByText('folder1');
    fireEvent.click(folder1Breadcrumb);

    expect(onFolderClick).toHaveBeenCalledWith('folder1');
  });

  it('calls onFolderClick with correct path for nested folders', () => {
    const onFolderClick = vi.fn();
    const props = {
      ...defaultProps,
      filePath: 'folder1/folder2/file.txt',
      onFolderClick,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // Click on the second folder breadcrumb
    const folder2Breadcrumb = screen.getByText('folder2');
    fireEvent.click(folder2Breadcrumb);

    expect(onFolderClick).toHaveBeenCalledWith('folder1/folder2');
  });

  it('does not make file breadcrumb clickable', () => {
    const onFolderClick = vi.fn();
    const props = {
      ...defaultProps,
      filePath: 'folder/file.txt',
      onFolderClick,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    // The file breadcrumb should be a span, not a button
    const fileBreadcrumb = screen.getByText('file.txt');
    expect(fileBreadcrumb.tagName).toBe('SPAN');
  });

  it('calls onFilesetClick when fileset breadcrumb is clicked', () => {
    const onFilesetClick = vi.fn();
    const props = {
      ...defaultProps,
      onFilesetClick,
    };

    render(
      <TestProviders>
        <FilesetFilePreviewPanel {...props} />
      </TestProviders>
    );

    const filesetBreadcrumb = screen.getByText('test-dataset');
    fireEvent.click(filesetBreadcrumb);

    expect(onFilesetClick).toHaveBeenCalledTimes(1);
  });
});
