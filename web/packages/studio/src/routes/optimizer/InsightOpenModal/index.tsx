// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, CodeSnippet, Modal, Stack, Text } from '@nvidia/foundations-react-core';
import type { Insight } from '@studio/api/optimizer';
import { LINK_DOCS_EXPERIMENTS_CLI } from '@studio/constants/links';
import { ChevronRight, File } from 'lucide-react';
import { type FC } from 'react';

/** Shell-escape a value interpolated into a single-quoted CLI argument. */
const shellQuote = (value: string): string => value.replace(/'/g, "'\\''");

/** CLI command that runs experiments to address an insight. */
const buildCliCommand = (insight: Insight): string =>
  `nemo exp run \\\n` +
  `  --insight '${shellQuote(insight.id)}' \\\n` +
  `  --dataset "<dataset-name>" \\\n` +
  `  --evaluators correctness,helpfulness,groundedness,tool-error`;

export interface InsightOpenModalProps {
  open: boolean;
  insight: Insight;
  /** Close the modal. */
  onClose: () => void;
}

export const InsightOpenModal: FC<InsightOpenModalProps> = ({ open, insight, onClose }) => {
  const cliCommand = buildCliCommand(insight);

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      slotHeading="Run experiment"
      className="w-[90vw] max-w-[720px]"
      attributes={{ ModalFooter: { className: 'justify-end' } }}
      slotFooter={
        <Button kind="primary" onClick={onClose}>
          Close
        </Button>
      }
    >
      <Stack gap="density-md">
        <Text kind="body/regular/md">
          Run the following CLI command to start experiments for this insight.
        </Text>
        <CodeSnippet value={cliCommand} language="bash" kind="block" className="w-full" />
        <Button
          asChild
          color="neutral"
          kind="tertiary"
          size="small"
          className="w-full justify-start"
        >
          <a href={LINK_DOCS_EXPERIMENTS_CLI} target="_blank" rel="noreferrer">
            <File className="!text-brand" />
            <Text className="flex-1">CLI docs — learn more</Text>
            <ChevronRight />
          </a>
        </Button>
      </Stack>
    </Modal>
  );
};
