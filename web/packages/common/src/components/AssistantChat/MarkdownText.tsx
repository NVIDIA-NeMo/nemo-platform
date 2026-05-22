// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeDisplay } from '@nemo/common/src/components/CodeDisplay';
import cn from 'classnames';
import { type FC, type ReactNode, useMemo } from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

export interface MarkdownTextProps {
  readonly content: string;
  readonly className?: string;
}

const isInlineCode = (children: ReactNode): boolean => {
  if (typeof children === 'string') return !children.includes('\n');
  if (Array.isArray(children))
    return !children.some((child) => typeof child === 'string' && child.includes('\n'));
  return true;
};

const extractLanguage = (className: string | undefined): string | null => {
  if (!className) return null;
  const match = /language-([\w-]+)/.exec(className);
  return match ? match[1] : null;
};

const childrenToText = (children: ReactNode): string => {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(childrenToText).join('');
  return '';
};

const components: Components = {
  h1: ({ children, ...rest }) => (
    <h1 className="mb-density-sm mt-density-md text-2xl font-semibold leading-tight" {...rest}>
      {children}
    </h1>
  ),
  h2: ({ children, ...rest }) => (
    <h2 className="mb-density-sm mt-density-md text-xl font-semibold leading-tight" {...rest}>
      {children}
    </h2>
  ),
  h3: ({ children, ...rest }) => (
    <h3 className="mb-density-xs mt-density-sm text-lg font-semibold leading-snug" {...rest}>
      {children}
    </h3>
  ),
  h4: ({ children, ...rest }) => (
    <h4 className="mb-density-xs mt-density-sm text-base font-semibold leading-snug" {...rest}>
      {children}
    </h4>
  ),
  h5: ({ children, ...rest }) => (
    <h5
      className="mb-density-xs mt-density-sm text-sm font-semibold uppercase tracking-wide"
      {...rest}
    >
      {children}
    </h5>
  ),
  h6: ({ children, ...rest }) => (
    <h6
      className="mb-density-xs mt-density-sm text-xs font-semibold uppercase tracking-wide text-fg-muted"
      {...rest}
    >
      {children}
    </h6>
  ),
  p: ({ children, ...rest }) => (
    <p className="mb-density-sm text-sm leading-[1.6] last:mb-0" {...rest}>
      {children}
    </p>
  ),
  a: ({ children, href, ...rest }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-fg-link underline-offset-2 hover:underline"
      {...rest}
    >
      {children}
    </a>
  ),
  ul: ({ children, ...rest }) => (
    <ul className="mb-density-sm ml-density-md list-disc space-y-density-2xs text-sm" {...rest}>
      {children}
    </ul>
  ),
  ol: ({ children, ...rest }) => (
    <ol className="mb-density-sm ml-density-md list-decimal space-y-density-2xs text-sm" {...rest}>
      {children}
    </ol>
  ),
  li: ({ children, ...rest }) => (
    <li className="leading-[1.6] [&>p]:mb-0" {...rest}>
      {children}
    </li>
  ),
  blockquote: ({ children, ...rest }) => (
    <blockquote
      className="my-density-sm border-l-2 border-base pl-density-sm text-sm italic text-fg-muted"
      {...rest}
    >
      {children}
    </blockquote>
  ),
  hr: ({ ...rest }) => <hr className="my-density-md border-base" {...rest} />,
  table: ({ children, ...rest }) => (
    <div className="my-density-sm overflow-x-auto">
      <table className="w-full border-collapse text-sm" {...rest}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...rest }) => (
    <thead className="border-b border-base bg-surface-sunken" {...rest}>
      {children}
    </thead>
  ),
  th: ({ children, ...rest }) => (
    <th
      className="border-b border-base px-density-sm py-density-xs text-left font-semibold"
      {...rest}
    >
      {children}
    </th>
  ),
  td: ({ children, ...rest }) => (
    <td className="border-b border-base px-density-sm py-density-xs align-top" {...rest}>
      {children}
    </td>
  ),
  strong: ({ children, ...rest }) => (
    <strong className="font-semibold" {...rest}>
      {children}
    </strong>
  ),
  em: ({ children, ...rest }) => (
    <em className="italic" {...rest}>
      {children}
    </em>
  ),
  code: ({ children, className, ...rest }) => {
    if (isInlineCode(children) && !extractLanguage(className)) {
      return (
        <code
          className="rounded bg-surface-sunken px-density-2xs py-[0.1em] font-mono text-[0.9em]"
          {...rest}
        >
          {children}
        </code>
      );
    }
    const language = extractLanguage(className);
    const raw = childrenToText(children).replace(/\n$/, '');
    return <CodeDisplay>{language ? `${language}\n${raw}` : raw}</CodeDisplay>;
  },
  pre: ({ children }) => <>{children}</>,
};

const REMARK_PLUGINS = [remarkGfm];

export const MarkdownText: FC<MarkdownTextProps> = ({ content, className }) => {
  // react-markdown re-parses on every change; memo'ing the plugin array keeps the cache stable.
  const plugins = useMemo(() => REMARK_PLUGINS, []);
  return (
    <div
      data-testid="assistant-chat-markdown"
      className={cn('text-sm leading-[1.6] text-fg-base', className)}
    >
      <Markdown components={components} remarkPlugins={plugins}>
        {content}
      </Markdown>
    </div>
  );
};
