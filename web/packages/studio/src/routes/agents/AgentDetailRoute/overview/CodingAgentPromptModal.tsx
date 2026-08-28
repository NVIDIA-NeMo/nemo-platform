// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Button, Flex, Modal, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { Copy } from 'lucide-react';
import { type FC, lazy, Suspense, useState } from 'react';

const CodeEditor = lazy(() =>
  import('@nemo/common/src/components/CodeEditor').then((module) => ({
    default: module.CodeEditor,
  }))
);

const editorFallback = (
  <Flex align="center" justify="center" className="h-64">
    <Spinner size="medium" aria-label="Loading editor..." />
  </Flex>
);

interface CodingAgentPromptModalProps {
  open: boolean;
  onClose: () => void;
  heading: string;
  description: string;
  /** Starting point for the prompt. Editable before copying. */
  prompt: string;
}

/** Shows the coding agent prompt for a "Get started" option, editable before copying. */
export const CodingAgentPromptModal: FC<CodingAgentPromptModalProps> = ({
  open,
  onClose,
  heading,
  description,
  prompt,
}) => {
  const { success, error } = useToast();
  const [content, setContent] = useState(prompt);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(content);
      success('Prompt copied — paste it into your coding agent.');
    } catch {
      error('Error copying prompt to clipboard');
    }
  };

  return (
    <Modal
      open={open}
      onOpenChange={onClose}
      className="w-[720px]"
      slotHeading={
        <Stack gap="1">
          <Text kind="title/sm">{heading}</Text>
          <Text kind="body/regular/sm" className="text-secondary">
            {description}
          </Text>
        </Stack>
      }
      slotFooter={
        <Button color="brand" kind="primary" onClick={onClose}>
          Close
        </Button>
      }
    >
      <Stack gap="2" className="h-64">
        <Suspense fallback={editorFallback}>
          <CodeEditor
            content={content}
            contentType={ContentType.TEXT}
            onChange={setContent}
            className="h-full min-h-0"
            hideLineNumbers
            hideFoldGutter
            hideLinter
            hideCopyButton
            slotLabel={<Text kind="body/semibold/sm">Coding agent prompt</Text>}
            slotControls={
              <Button
                kind="tertiary"
                size="tiny"
                aria-label="Copy to clipboard"
                onClick={copyToClipboard}
              >
                <Copy size={16} className="text-brand" aria-hidden />
              </Button>
            }
          />
        </Suspense>
      </Stack>
    </Modal>
  );
};
