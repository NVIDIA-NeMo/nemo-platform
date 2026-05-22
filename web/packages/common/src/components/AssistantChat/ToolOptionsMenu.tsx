// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { StudioToolRegistry } from '@nemo/common/src/components/AssistantChat/tools/types';
import { Button, Divider, Popover, Stack, Switch, Text } from '@nvidia/foundations-react-core';
import { SlidersHorizontal } from 'lucide-react';

interface ToolOptionsMenuProps {
  readonly tools: StudioToolRegistry;
  readonly enabled: ReadonlySet<string>;
  readonly onToggle: (toolName: string, enabled: boolean) => void;
  readonly disabled?: boolean;
}

export const ToolOptionsMenu = ({ tools, enabled, onToggle, disabled }: ToolOptionsMenuProps) => {
  if (!tools.length) return null;

  const enabledCount = tools.reduce((count, tool) => count + (enabled.has(tool.name) ? 1 : 0), 0);

  return (
    <Popover
      slotContent={
        <Stack
          gap="density-sm"
          className="w-72 p-density-sm"
          data-testid="assistant-chat-tool-options"
        >
          <Stack gap="density-xs">
            <Text kind="label/bold/sm">Tools</Text>
            <Text kind="body/regular/sm" className="text-fg-muted">
              Enable tools the model can call during this thread.
            </Text>
          </Stack>
          <Divider />
          <Stack gap="density-sm">
            {tools.map((tool) => {
              const isEnabled = enabled.has(tool.name);
              return (
                <label
                  key={tool.name}
                  className="flex cursor-pointer items-start justify-between gap-density-sm"
                  data-testid={`assistant-chat-tool-toggle-${tool.name}`}
                >
                  <Stack gap="density-xs" className="min-w-0">
                    <Text kind="label/regular/sm">{tool.label}</Text>
                    <Text kind="body/regular/sm" className="text-fg-muted">
                      {tool.description.length > 120
                        ? `${tool.description.slice(0, 117).trimEnd()}…`
                        : tool.description}
                    </Text>
                  </Stack>
                  <Switch
                    checked={isEnabled}
                    onCheckedChange={(next) => onToggle(tool.name, next)}
                    aria-label={`Toggle ${tool.label}`}
                  />
                </label>
              );
            })}
          </Stack>
        </Stack>
      }
    >
      <Button
        aria-label="Tool options"
        title={
          enabledCount > 0
            ? `${enabledCount} tool${enabledCount === 1 ? '' : 's'} enabled`
            : 'Tools'
        }
        kind="tertiary"
        size="small"
        type="button"
        disabled={disabled}
        data-testid="assistant-chat-tool-options-trigger"
        data-active={enabledCount > 0}
      >
        <SlidersHorizontal size={16} />
        {enabledCount > 0 ? (
          <Text kind="label/regular/xs" className="ml-density-xs">
            {enabledCount}
          </Text>
        ) : null}
      </Button>
    </Popover>
  );
};
