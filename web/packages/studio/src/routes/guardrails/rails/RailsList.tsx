// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { Badge, Button, Flex, Stack, Switch, Text, Tooltip } from '@nvidia/foundations-react-core';
import { RAIL_DEFINITIONS } from '@studio/routes/guardrails/rails/registry';
import type { RailDefinition, RailScope } from '@studio/routes/guardrails/rails/types';
import { Settings, Trash2 } from 'lucide-react';
import type { FC } from 'react';

const SCOPE_LABELS: Record<RailScope, string> = {
  input: 'Input',
  output: 'Output',
  retrieval: 'Retrieval',
};

export interface RailsListProps {
  data: RailsConfig;
  onChange: (next: RailsConfig) => void;
  onConfigure: (rail: RailDefinition) => void;
}

/**
 * The guardrails a config can run, each with a switch and its own settings.
 *
 * Rails are listed whether or not the config uses them, so turning one on is a single
 * click rather than a hunt — and the switch performs every edit the engine needs at once
 * (flow, prompt, and task model), which is what makes the coupling invisible here.
 */
export const RailsList: FC<RailsListProps> = ({ data, onChange, onConfigure }) => (
  <Stack gap="0" role="list">
    {RAIL_DEFINITIONS.map((rail) => (
      <RailRow
        key={rail.id}
        rail={rail}
        data={data}
        onChange={onChange}
        onConfigure={onConfigure}
      />
    ))}
  </Stack>
);

interface RailRowProps extends RailsListProps {
  rail: RailDefinition;
}

const RailRow: FC<RailRowProps> = ({ rail, data, onChange, onConfigure }) => {
  const enabled = rail.isEnabled(data);
  // Offered only when switching off left settings behind, so the row stays quiet in the
  // common case and the action appears exactly when there is something to discard.
  const canDiscard = !enabled && rail.hasStoredSettings(data);

  return (
    <Flex
      role="listitem"
      align="center"
      gap="density-lg"
      className="border-border-subtle border-b py-density-md last:border-b-0"
    >
      <Switch
        checked={enabled}
        onCheckedChange={(next) => onChange(rail.setEnabled(data, next))}
        attributes={{ SwitchInput: { 'aria-label': rail.label } }}
      />

      <Text kind="label/bold/md" className="w-[180px] shrink-0">
        {rail.label}
      </Text>

      {/* The stages this rail is capable of running at — they describe the rail, not the
          current setting, so they stay visible when it is switched off. */}
      <Flex align="center" gap="density-xs" wrap="wrap" className="flex-1">
        {rail.scopes.map((scope) => (
          <Badge key={scope} color="gray" kind="outline">
            {SCOPE_LABELS[scope]}
          </Badge>
        ))}
      </Flex>

      {canDiscard ? (
        <Tooltip slotContent={`Discard saved ${rail.label} settings`}>
          <Button
            kind="tertiary"
            color="neutral"
            onClick={() => onChange(rail.clearSettings(data))}
            aria-label={`Discard saved ${rail.label} settings`}
          >
            <Trash2 size={16} />
          </Button>
        </Tooltip>
      ) : null}

      <Tooltip slotContent={`Configure ${rail.label}`}>
        <Button
          kind="tertiary"
          color="neutral"
          onClick={() => onConfigure(rail)}
          aria-label={`Configure ${rail.label}`}
        >
          <Settings size={16} />
        </Button>
      </Tooltip>
    </Flex>
  );
};
