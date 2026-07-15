// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useStickToBottom } from '@nemo/common/src/hooks/useStickToBottom';
import { triggerDownload } from '@nemo/common/src/utils/file';
import { formatLogs } from '@nemo/common/src/utils/logs';
import type { PlatformJobLog } from '@nemo/sdk/generated/platform/schema';
import {
  Block,
  Button,
  CodeSnippet,
  Flex,
  Spinner,
  Tag,
  Text,
} from '@nvidia/foundations-react-core';
import classNames from 'classnames';
import { ArrowUp, Download } from 'lucide-react';
import { FC, useMemo, useState } from 'react';

const DEFAULT_ROW_COUNT = 30;

interface LogViewerProps {
  logs: PlatformJobLog[];
  isLoading?: boolean;
  downloadFilename?: string;
  rows?: number;
  emptyMessage?: string;
}

export const LogViewer: FC<LogViewerProps> = ({
  logs,
  isLoading = false,
  downloadFilename,
  rows = DEFAULT_ROW_COUNT,
  emptyMessage = 'No logs available yet',
}) => {
  const [showAllLogs, setShowAllLogs] = useState(false);
  const tailLogs = logs?.slice(-rows) || [];
  const displayedLogs = showAllLogs ? logs : tailLogs;
  const logText = formatLogs(displayedLogs);
  const hasMoreLogs = logs && logs.length > rows;

  const isShowingLogs = useMemo(() => logs.length > 0 && !isLoading, [logs.length, isLoading]);

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
    return <Spinner size="medium" aria-label="Loading..." />;
  }

  if (!logs || logs.length === 0) {
    return <Block className="text-subtle">{emptyMessage}</Block>;
  }

  return (
    <Block className="relative overflow-hidden">
      {!showAllLogs && hasMoreLogs && (
        <Block className="absolute top-6 mt-[2px] left-px right-px z-10 py-5 text-center bg-[linear-gradient(to_bottom,var(--background-color-surface-sunken),transparent)]">
          <Tag color="gray" kind="solid" onClick={handleLoadMore}>
            <ArrowUp />
            Load previous logs
          </Tag>
        </Block>
      )}
      <CodeSnippet
        language="shell"
        value={logText}
        kind="block"
        collapsible={false}
        rows={rows}
        attributes={{
          CodeSnippetCode: {
            ref: codeScrollRef,
            className: classNames({ '!overflow-y-hidden': !showAllLogs }),
          },
        }}
        slotActions={
          <Flex className="w-full" justify="between" wrap="wrap">
            <Text kind="mono/md">
              {displayedLogs.length} {!showAllLogs && hasMoreLogs && `of ${logs.length}`} lines
            </Text>
            {downloadFilename && (
              <Flex gap="density-sm">
                <Button size="tiny" kind="tertiary" onClick={handleDownload}>
                  <Download />
                </Button>
              </Flex>
            )}
          </Flex>
        }
      />
    </Block>
  );
};
