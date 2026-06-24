// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, Stack, Text, Tooltip } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import {
  ArtifactRow,
  FileArtifacts,
  JobArtifacts,
  LinkArtifacts,
  SelectionArtifacts,
  ToolArtifacts,
} from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/ArtifactSections';
import {
  getSelectedArtifactModel,
  hasArtifacts,
} from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/helpers';
import type { ClaudeCodeChatArtifacts } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { Bot, Boxes, Cpu, PanelRightClose, Sparkles } from 'lucide-react';

export const ClaudeCodeArtifactsPane = ({
  artifacts,
  collapseLabel,
  onCollapse,
}: {
  artifacts?: ClaudeCodeChatArtifacts;
  collapseLabel: string;
  onCollapse: () => void;
}) => {
  const selectedModel = artifacts ? getSelectedArtifactModel(artifacts) : undefined;

  return (
    <section className="flex min-h-0 basis-1/2 flex-col border-b border-base">
      <Flex
        align="center"
        justify="between"
        gap="density-sm"
        className="border-b border-base px-density-md py-density-sm"
      >
        <Flex align="center" gap="density-sm" className="min-w-0">
          <Sparkles size={18} className="shrink-0 text-secondary" />
          <Text kind="label/bold/md" className="truncate">
            Chat artifacts
          </Text>
        </Flex>
        <Tooltip slotContent={collapseLabel} side="left">
          <Button
            aria-label={collapseLabel}
            kind="tertiary"
            size="small"
            type="button"
            onClick={onCollapse}
          >
            <PanelRightClose size={18} />
          </Button>
        </Tooltip>
      </Flex>
      {hasArtifacts(artifacts) ? (
        <Stack gap="density-md" padding="density-md" className="min-h-0 flex-1 overflow-y-auto">
          <Stack gap="density-sm" className="min-w-0">
            <ArtifactRow icon={<Bot size={14} />} label="Agent" value={artifacts.agent} />
            <ArtifactRow icon={<Cpu size={14} />} label="Model" value={selectedModel} />
            <ArtifactRow icon={<Boxes size={14} />} label="Workspace" value={artifacts.workspace} />
          </Stack>
          <SelectionArtifacts selections={artifacts.selections} />
          <JobArtifacts jobs={artifacts.jobs} workspace={artifacts.workspace} />
          <FileArtifacts files={artifacts.files} />
          <LinkArtifacts links={artifacts.links} />
          <ToolArtifacts tools={artifacts.tools} />
        </Stack>
      ) : (
        <Flex className="min-h-0 flex-1 px-density-md" align="center" justify="center">
          <Empty title="No artifacts yet" description="Selections and outputs will appear here." />
        </Flex>
      )}
    </section>
  );
};
