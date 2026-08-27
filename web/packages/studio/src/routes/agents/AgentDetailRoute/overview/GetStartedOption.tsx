// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Block, Button, Flex, StatusMessage } from '@nvidia/foundations-react-core';
import { MessageSquareText } from 'lucide-react';
import type { FC } from 'react';

interface GetStartedOptionProps {
  heading: string;
  description: string;
  /** Copied verbatim for the user to paste into their coding agent. */
  prompt: string;
  /** Distinguishes the two identically-labelled buttons for screen readers. */
  actionLabel: string;
}

/** One way to connect an agent to the platform, with the prompt that does it. */
export const GetStartedOption: FC<GetStartedOptionProps> = ({
  heading,
  description,
  prompt,
  actionLabel,
}) => {
  const { success, error } = useToast();

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      success('Prompt copied — paste it into your coding agent.', { durationMs: 3000 });
    } catch {
      error('Error copying prompt to clipboard', { durationMs: 3000 });
    }
  };

  return (
    <Flex justify="center" className="min-w-0 flex-1 basis-80">
      <StatusMessage
        size="small"
        slotHeading={heading}
        slotSubheading={<Block className="max-w-[34rem]">{description}</Block>}
        slotFooter={
          <Button kind="tertiary" aria-label={actionLabel} onClick={copyPrompt}>
            <MessageSquareText size={16} className="text-brand" aria-hidden />
            Get coding agent prompt
          </Button>
        }
      />
    </Flex>
  );
};
