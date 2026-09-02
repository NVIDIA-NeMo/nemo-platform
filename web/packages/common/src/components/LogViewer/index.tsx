// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useStickToBottom } from '@nemo/common/src/hooks/useStickToBottom';
import type { NotifyFn } from '@nemo/common/src/providers/toast/types';
import { useNotify } from '@nemo/common/src/providers/toast/useNotify';
import { triggerDownload } from '@nemo/common/src/utils/file';
import { formatLogs } from '@nemo/common/src/utils/logs';
import type { PlatformJobLog } from '@nemo/sdk/generated/platform/schema';
import {
  Block,
  Button,
  CodeSnippetActions,
  CodeSnippetCode,
  CodeSnippetCopyButton,
  CodeSnippetRoot,
  Flex,
  Spinner,
  Tag,
  Text,
} from '@nvidia/foundations-react-core';
import classNames from 'classnames';
import { ArrowUp, Copy, Download, WrapText } from 'lucide-react';
import { FC, useMemo, useState } from 'react';

const DEFAULT_ROW_COUNT = 30;

interface LogViewerProps {
  logs: PlatformJobLog[];
  isLoading?: boolean;
  downloadFilename?: string;
  rows?: number;
  fillHeight?: boolean;
  emptyMessage?: string;
  /** Where the copy confirmation goes. Defaults to the surrounding ToastProvider; plugins pass `host.notifications.notify`. */
  onNotify?: NotifyFn;
}

export const LogViewer: FC<LogViewerProps> = ({
  logs,
  isLoading = false,
  downloadFilename,
  rows = DEFAULT_ROW_COUNT,
  fillHeight = false,
  emptyMessage = 'No logs available yet',
  onNotify,
}) => {
  const [showAllLogs, setShowAllLogs] = useState(fillHeight);
  const [wrapLines, setWrapLines] = useState(false);
  const tailLogs = logs?.slice(-rows) || [];
  const displayedLogs = showAllLogs ? logs : tailLogs;
  const logText = formatLogs(displayedLogs);
  const hasMoreLogs = logs && logs.length > rows;

  const isShowingLogs = useMemo(() => logs.length > 0 && !isLoading, [logs.length, isLoading]);

  const notify = useNotify(onNotify);

  const { ref: codeScrollRef, scrollToBottom } = useStickToBottom<HTMLDivElement>({
    enabled: isShowingLogs,
    resetKey: showAllLogs,
  });

  const handleDownload = () => {
    if (downloadFilename) {
      triggerDownload(formatLogs(logs), downloadFilename);
    }
  };

  const handleLoadMore = () => {
    scrollToBottom();
    setShowAllLogs(true);
  };

  if (isLoading) {
    return (
      <Flex align="center" justify="center" className="h-full min-h-32 w-full">
        <Spinner size="medium" aria-label="Loading..." />
      </Flex>
    );
  }

  if (!logs || logs.length === 0) {
    return (
      <Flex align="center" justify="center" className="h-full min-h-32 w-full">
        <Block className="text-subtle">{emptyMessage}</Block>
      </Flex>
    );
  }

  return (
    <Block className="relative w-full min-w-0 max-w-full overflow-hidden h-full">
      {!showAllLogs && hasMoreLogs && (
        <Block className="absolute top-6 mt-[2px] left-px right-px z-10 py-5 text-center bg-[linear-gradient(to_bottom,var(--background-color-surface-sunken),transparent)]">
          <Tag color="gray" kind="solid" onClick={handleLoadMore}>
            <ArrowUp />
            Load previous logs
          </Tag>
        </Block>
      )}
      <CodeSnippetRoot
        kind="block"
        collapsible={false}
        rows={fillHeight ? undefined : rows}
        className="min-h-auto h-full"
      >
        <CodeSnippetActions>
          <Flex className="w-full" justify="between" wrap="wrap">
            <Text kind="mono/md">
              {displayedLogs.length} {!showAllLogs && hasMoreLogs && `of ${logs.length}`} lines
            </Text>
            <Flex gap="0.25">
              <Button
                size="tiny"
                kind={wrapLines ? 'secondary' : 'tertiary'}
                title="Wrap lines"
                aria-label="Wrap lines"
                aria-pressed={wrapLines}
                onClick={() => setWrapLines((prev) => !prev)}
              >
                <WrapText />
              </Button>
              {downloadFilename && (
                <Button
                  size="tiny"
                  kind="tertiary"
                  title="Download logs"
                  aria-label="Download logs"
                  onClick={handleDownload}
                >
                  <Download />
                </Button>
              )}
            </Flex>
          </Flex>
          <CodeSnippetCopyButton
            value={logText}
            title="Copy logs"
            aria-label="Copy logs"
            onClick={() => notify('Copied to clipboard!', 'success', { durationMs: 3000 })}
          >
            <Copy />
          </CodeSnippetCopyButton>
        </CodeSnippetActions>
        <CodeSnippetCode
          value={logText}
          language="shell"
          ref={codeScrollRef}
          className={classNames(
            'min-w-0 max-w-full',
            { 'h-full !overflow-y-auto': fillHeight },
            // Keep scroll on when wrapping: wrapped rows exceed the fixed height.
            { '!overflow-y-hidden': !showAllLogs && !wrapLines },
            {
              'whitespace-pre-wrap [overflow-wrap:anywhere] [&_code]:whitespace-pre-wrap [&_pre]:whitespace-pre-wrap [&_pre]:[overflow-wrap:anywhere]':
                wrapLines,
            }
          )}
        />
      </CodeSnippetRoot>
    </Block>
  );
};
