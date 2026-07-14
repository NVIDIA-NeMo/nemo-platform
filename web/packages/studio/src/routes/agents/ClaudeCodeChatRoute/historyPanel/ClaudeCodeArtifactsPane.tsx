// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Divider, Flex, Stack, Text, Tooltip } from '@nvidia/foundations-react-core';
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
import { PanelRightClose } from 'lucide-react';
import { Fragment, type ReactNode } from 'react';

interface ArtifactPaneSection {
  content: ReactNode;
  id: string;
}

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
  const sections: ArtifactPaneSection[] = [];

  if (artifacts?.agent || selectedModel) {
    sections.push({
      id: 'summary',
      content: (
        <Stack gap="density-sm" className="min-w-0">
          <ArtifactRow label="Agent" value={artifacts?.agent} />
          <ArtifactRow label="Model" value={selectedModel} />
        </Stack>
      ),
    });
  }

  if (artifacts?.selections.length) {
    sections.push({
      id: 'selections',
      content: <SelectionArtifacts selections={artifacts.selections} />,
    });
  }

  if (artifacts?.jobs.length) {
    sections.push({
      id: 'jobs',
      content: <JobArtifacts jobs={artifacts.jobs} workspace={artifacts.workspace} />,
    });
  }

  if (artifacts?.files.length) {
    sections.push({ id: 'files', content: <FileArtifacts files={artifacts.files} /> });
  }

  if (artifacts?.links.length) {
    sections.push({ id: 'links', content: <LinkArtifacts links={artifacts.links} /> });
  }

  if (artifacts?.tools.length) {
    sections.push({ id: 'tools', content: <ToolArtifacts tools={artifacts.tools} /> });
  }

  return (
    <section
      aria-label="Chat artifacts"
      className="flex min-h-0 basis-1/2 shrink-0 flex-col overflow-hidden rounded border border-base bg-surface-base dark:bg-surface-raised"
    >
      <Flex
        align="center"
        justify="between"
        gap="density-sm"
        className="border-b border-base px-density-md py-density-sm"
      >
        <Text kind="label/bold/md" className="min-w-0 truncate">
          Chat artifacts
        </Text>
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
        <Stack gap="density-sm" padding="density-md" className="min-h-0 flex-1 overflow-y-auto">
          {sections.map((section, index) => (
            <Fragment key={section.id}>
              {index > 0 && <Divider />}
              {section.content}
            </Fragment>
          ))}
        </Stack>
      ) : (
        <Flex className="min-h-0 flex-1 px-density-md" align="center" justify="center">
          <Empty title="No artifacts yet" description="Selections and outputs will appear here." />
        </Flex>
      )}
    </section>
  );
};
