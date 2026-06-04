// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { decode } from 'html-entities';
import { type FC, type PropsWithChildren, useMemo } from 'react';
import Markdown from 'react-markdown';

import { splitMessageWithLabels } from './utils';
import { simpleHash } from '../../../utils/simpleHash';
import { CodeDisplay } from '../../CodeDisplay';

export interface MessageContentProps {
  content?: string | null;
  renderAsMarkdown?: boolean;
}

const INLINE_CODE_CLASS =
  'rounded bg-gray-050 px-1 py-0.5 font-mono text-[0.95em] dark:bg-gray-900';

/**
 * This component takes a content string from a chat response and converts into a user readable
 * list of snippets using content-specific render types. Currently supports plaintext and code.
 */
export const MessageContent: FC<PropsWithChildren<MessageContentProps>> = ({
  content,
  renderAsMarkdown = true,
}) => {
  const snippets = useMemo(() => splitMessageWithLabels(content), [content]);
  return snippets.map((descriptor) => {
    const contentHash = simpleHash(descriptor.value);
    if (descriptor.type === 'plaintext') {
      return (
        <div
          className="text-base font-normal leading-[150%] text-sm"
          data-testid="chat-message-content-text"
          key={`plaintext-${contentHash}`}
        >
          {renderAsMarkdown ? (
            <Markdown
              components={{
                // We don't want links embedded in markdown responses to be clickable
                a: ({ ...props }) => <span>{props.children}</span>,
                code: ({ children }) => <code className={INLINE_CODE_CLASS}>{children}</code>,
              }}
            >
              {decode(descriptor.value)}
            </Markdown>
          ) : (
            <Text kind="mono/md" className="whitespace-pre-wrap">
              {decode(descriptor.value)}
            </Text>
          )}
        </div>
      );
    } else if (descriptor.type === 'code') {
      return (
        <Stack key={`code-${contentHash}`}>
          {renderAsMarkdown ? (
            <CodeDisplay data-testid="chat-message-content-text">{descriptor.value}</CodeDisplay>
          ) : (
            <Text kind="mono/md" className="whitespace-pre-wrap">
              {descriptor.value}
            </Text>
          )}
        </Stack>
      );
    }
  });
};
