// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MessagePrimitive } from '@assistant-ui/react';
import type { MessageRenderProps } from '@nemo/common/src/components/AssistantChat/types';
import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import { Banner } from '@nvidia/foundations-react-core';

export const AssistantChatMessageContent = ({
  messageContentProps,
  toolCallPartComponent,
}: MessageRenderProps) => (
  <>
    <MessagePrimitive.Parts
      components={{
        Text: ({ text }) => <MessageContent content={text} {...messageContentProps} />,
        Image: ({ image, filename }) => (
          <img
            src={image}
            alt={filename ?? 'Attached image'}
            className="mt-density-xs max-h-64 w-auto rounded-lg border border-base object-contain"
          />
        ),
        tools: { Fallback: toolCallPartComponent },
      }}
    />
    <MessagePrimitive.Error>
      <Banner kind="inline" status="error" className="mt-density-sm">
        There was an error generating a response.
      </Banner>
    </MessagePrimitive.Error>
  </>
);
