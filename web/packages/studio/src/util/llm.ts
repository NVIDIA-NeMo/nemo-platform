// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ExcludedChatCompletionMessageParam } from '@nemo/common/src/types/chat';
import { Row } from '@studio/util/files';
import { logger } from '@studio/util/logger';
import Handlebars from 'handlebars';

export const extractUserMessage = (props: { row: Row; template?: string }): string => {
  const { row, template } = props;
  // Try direct extraction from expected path
  const messages = row?.messages as ExcludedChatCompletionMessageParam[] | undefined;
  if (messages) {
    const userMessage = messages.find((message) => message.role === 'user');
    if (userMessage) {
      return userMessage.content as string;
    }
  }
  if (template) {
    try {
      const compiled = Handlebars.compile(template);
      return compiled(row);
    } catch (err) {
      logger.error('Failed to compile template', err);
      return '';
    }
  }
  return '';
};
