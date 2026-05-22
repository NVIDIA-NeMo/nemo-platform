// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MarkdownText } from '@nemo/common/src/components/AssistantChat/MarkdownText';
import {
  ThemeProvider as KaizenThemeProvider,
  TooltipProvider,
} from '@nvidia/foundations-react-core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';

const renderMarkdown = (element: ReactElement) =>
  render(
    <KaizenThemeProvider className="h-full" density="standard" theme="light">
      <TooltipProvider>{element}</TooltipProvider>
    </KaizenThemeProvider>
  );

describe('MarkdownText', () => {
  it('renders headings, paragraphs, and emphasis', () => {
    renderMarkdown(<MarkdownText content={'# Title\n\nSome **bold** and *italic* text.'} />);

    expect(screen.getByRole('heading', { name: 'Title', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('bold').tagName).toBe('STRONG');
    expect(screen.getByText('italic').tagName).toBe('EM');
  });

  it('renders ordered and unordered lists', () => {
    renderMarkdown(<MarkdownText content={'- one\n- two\n\n1. first\n2. second'} />);

    const unordered = screen.getAllByRole('list');
    expect(unordered).toHaveLength(2);
    expect(screen.getByText('first')).toBeInTheDocument();
    expect(screen.getByText('two')).toBeInTheDocument();
  });

  it('renders GFM tables', () => {
    renderMarkdown(
      <MarkdownText content={'| Header A | Header B |\n| --- | --- |\n| Cell 1 | Cell 2 |'} />
    );

    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Header A' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Cell 2' })).toBeInTheDocument();
  });

  it('renders inline code distinctly from fenced code blocks', () => {
    renderMarkdown(
      <MarkdownText content={'Use `npm install` for setup.\n\n```ts\nconst x = 1;\n```'} />
    );

    const inline = screen.getByText('npm install');
    expect(inline.tagName).toBe('CODE');

    // Fenced block goes through CodeDisplay.
    expect(screen.getByTestId('code-display')).toBeInTheDocument();
  });

  it('opens markdown links in a new tab with rel=noopener', () => {
    renderMarkdown(<MarkdownText content="[NeMo](https://example.com/nemo)" />);

    const link = screen.getByRole('link', { name: 'NeMo' });
    expect(link).toHaveAttribute('href', 'https://example.com/nemo');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
  });

  it('renders blockquotes and horizontal rules', () => {
    renderMarkdown(<MarkdownText content={'> quoted text\n\n---'} />);

    const quoted = screen.getByText('quoted text');
    expect(quoted.tagName).toBe('P');
    expect(screen.getByRole('separator')).toBeInTheDocument();
  });
});
