// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Divider, Stack, Text } from '@nvidia/foundations-react-core';
import { JsonConfigPanel } from '@studio/components/CreateCustomizationStart/JsonConfigPanel';
import { TemplateGrid } from '@studio/components/CreateCustomizationStart/TemplateGrid';
import type { StartOptionDetailProps } from '@studio/components/CreateCustomizationStart/types';
import type { FC, ReactNode } from 'react';

/**
 * The secondary area under the start tiles, holding whatever the chosen option still
 * needs from the user. "Build from scratch" needs nothing, so it renders no detail at
 * all rather than filling the space with an explanation of the form it is about to open.
 */
export const StartOptionDetail: FC<StartOptionDetailProps> = ({
  option,
  workspace,
  selectedTemplate,
  onSelectTemplate,
  onValidConfig,
}) => {
  let content: ReactNode = null;

  if (option.id === 'template') {
    content = (
      <TemplateGrid
        workspace={workspace}
        selectedTemplate={selectedTemplate}
        onSelectTemplate={onSelectTemplate}
      />
    );
  } else if (option.id === 'json') {
    content = <JsonConfigPanel onValidConfig={onValidConfig} />;
  }

  if (!content) return null;

  return (
    <Stack gap="density-md" className="w-full">
      <Divider />
      <Text kind="label/bold/sm" className="text-secondary">
        {option.title}
      </Text>
      {content}
    </Stack>
  );
};
