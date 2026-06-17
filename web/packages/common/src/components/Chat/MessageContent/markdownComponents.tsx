// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { INLINE_CODE_CLASS } from '@nemo/common/src/components/Chat/MessageContent/constants';
import { renderListItemChildren } from '@nemo/common/src/components/Chat/MessageContent/helpers';
import { MarkdownDataViewTable } from '@nemo/common/src/components/Chat/MessageContent/MarkdownDataViewTable';
import { MarkdownParagraph } from '@nemo/common/src/components/Chat/MessageContent/MarkdownParagraph';
import { Text } from '@nvidia/foundations-react-core';
import cn from 'classnames';
import type { Components } from 'react-markdown';

export const messageMarkdownComponents: Components = {
  h1: ({ children }) => (
    <Text asChild kind="title/lg">
      <h1 className="mb-density-sm mt-density-3xl first:mt-0">{children}</h1>
    </Text>
  ),
  h2: ({ children }) => (
    <Text asChild kind="title/md">
      <h2 className="mb-density-sm mt-density-3xl first:mt-0">{children}</h2>
    </Text>
  ),
  h3: ({ children }) => (
    <Text asChild kind="label/bold/md">
      <h3 className="mb-density-sm mt-density-2xl first:mt-0">{children}</h3>
    </Text>
  ),
  h4: ({ children }) => (
    <Text asChild kind="label/bold/sm">
      <h4 className="mb-density-sm mt-density-md first:mt-0">{children}</h4>
    </Text>
  ),
  h5: ({ children }) => (
    <Text asChild kind="label/bold/sm">
      <h5 className="mb-density-sm mt-density-md first:mt-0">{children}</h5>
    </Text>
  ),
  h6: ({ children }) => (
    <Text asChild kind="label/bold/sm">
      <h6 className="mb-density-sm mt-density-md first:mt-0">{children}</h6>
    </Text>
  ),
  p: MarkdownParagraph,
  ul: ({ children, className }) => (
    <ul className={cn('my-density-xl list-disc pl-density-lg', className)}>{children}</ul>
  ),
  ol: ({ children, className, start }) => (
    <ol className={cn('my-density-xl list-decimal pl-density-2xl', className)} start={start}>
      {children}
    </ol>
  ),
  li: ({ children, className }) => (
    <li
      className={cn(
        'mb-density-sm whitespace-normal pl-density-xs text-sm leading-[160%] last:mb-0 [&>p]:my-0',
        className
      )}
    >
      {renderListItemChildren(children)}
    </li>
  ),
  hr: () => <hr className="my-density-sm border-base" />,
  blockquote: ({ children, className }) => (
    <blockquote
      className={cn('my-density-xs border-l-4 border-base pl-density-sm text-secondary', className)}
    >
      {children}
    </blockquote>
  ),
  img: ({ src, alt }) => <img src={src} alt={alt ?? ''} className="max-w-full" />,
  // Most chat surfaces keep model-supplied links inert. Consumers that know how
  // to handle links can provide their own renderer.
  a: ({ children }) => <span>{children}</span>,
  code: ({ children }) => <code className={INLINE_CODE_CLASS}>{children}</code>,
  table: ({ children }) => <MarkdownDataViewTable>{children}</MarkdownDataViewTable>,
};
