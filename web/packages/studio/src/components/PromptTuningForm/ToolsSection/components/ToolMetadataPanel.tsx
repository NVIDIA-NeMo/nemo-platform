// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { ChatCompletionToolsParam } from '@nemo/common/src/zod/tools';
import {
  Flex,
  SidePanelContent,
  SidePanelDialog,
  SidePanelHeading,
  SidePanelRoot,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { ToolParameterDetails } from '@studio/components/PromptTuningForm/ToolsSection/components/ToolParameterDetails';
import { Wrench } from 'lucide-react';
import { ComponentProps, FC } from 'react';

export interface ToolMetadataPanelProps {
  open: boolean;
  tool?: ChatCompletionToolsParam;
  onClose: () => void;
  attributes?: {
    SidePanelRoot?: ComponentProps<typeof SidePanelRoot>;
    SidePanelContent?: ComponentProps<typeof SidePanelContent>;
    SidePanelHeading?: ComponentProps<typeof SidePanelHeading>;
  };
}

export const ToolMetadataPanel: FC<ToolMetadataPanelProps> = ({
  open,
  tool,
  onClose,
  attributes,
}) => {
  if (!tool) {
    return null;
  }

  const toolJson = JSON.stringify(tool, null, 2);

  return (
    <SidePanelRoot open={open} onOpenChange={onClose} modal {...attributes?.SidePanelRoot}>
      <SidePanelDialog>
        <SidePanelContent className="w-[800px]" bordered {...attributes?.SidePanelContent}>
          <SidePanelHeading {...attributes?.SidePanelHeading}>
            <Flex gap="density-md" align="center">
              <Wrench />
              Tool Metadata
            </Flex>
          </SidePanelHeading>
          <Stack gap="density-2xl" padding="4" className="h-full overflow-y-auto">
            {/* Basic Information */}
            <Stack gap="density-xl">
              <Text kind="label/semibold/lg">Basic Information</Text>
              <Stack gap="density-md">
                <Stack gap="density-xs">
                  <Text kind="label/semibold/md">Function Name</Text>
                  <Text kind="label/regular/md">{tool.function.name}</Text>
                </Stack>
                {tool.function.description && (
                  <Stack gap="density-xs">
                    <Text kind="label/semibold/md">Description</Text>
                    <Text kind="label/regular/md">{tool.function.description}</Text>
                  </Stack>
                )}
              </Stack>
            </Stack>

            {/* Parameters */}
            <Stack gap="density-xl">
              <Text kind="label/semibold/lg">Parameters</Text>
              <ToolParameterDetails tool={tool} />
            </Stack>

            {/* JSON Schema */}
            <Stack gap="density-md" className="max-h-[500px]">
              <Text kind="label/semibold/lg">Definition</Text>
              <CodeEditor content={toolJson} readOnly contentType={ContentType.JSON} />
            </Stack>
          </Stack>
        </SidePanelContent>
      </SidePanelDialog>
    </SidePanelRoot>
  );
};
