// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MarkdownContent } from '@nemo/common/src/components/MarkdownContent';
import { Flex, Spinner, Text } from '@nvidia/foundations-react-core';
import { type FC } from 'react';

export interface ReadmeBodyProps {
  isFilesError: boolean;
  readmePath: string | undefined;
  isContentLoading: boolean;
  isContentError: boolean;
  content: string | undefined;
  filesErrorMessage?: string;
  noReadmeMessage?: string;
}

export const ReadmeBody: FC<ReadmeBodyProps> = ({
  isFilesError,
  readmePath,
  isContentLoading,
  isContentError,
  content,
  filesErrorMessage = 'Failed to load files.',
  noReadmeMessage = 'No README.md found at the root of this fileset.',
}) => {
  if (isFilesError) {
    return (
      <Flex className="min-h-80" align="center" justify="center">
        <Text className="text-feedback-danger">{filesErrorMessage}</Text>
      </Flex>
    );
  }

  if (!readmePath) {
    return (
      <Flex className="min-h-80" align="center" justify="center">
        <Text color="secondary">{noReadmeMessage}</Text>
      </Flex>
    );
  }

  if (isContentLoading) {
    return (
      <Flex className="min-h-80" align="center" justify="center">
        <Spinner description="Loading README..." />
      </Flex>
    );
  }

  if (isContentError || content === undefined) {
    return (
      <Flex className="min-h-80" align="center" justify="center">
        <Text className="text-feedback-danger">Failed to load README.</Text>
      </Flex>
    );
  }

  return <MarkdownContent content={content} />;
};
