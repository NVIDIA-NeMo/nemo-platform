// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { Badge, Button, Flex, Stack, Switch, Text, Tooltip } from '@nvidia/foundations-react-core';
import { RAIL_DEFINITIONS } from '@studio/routes/guardrails/rails/registry';
import type { RailDefinition, RailScope } from '@studio/routes/guardrails/rails/types';
import { Trash2 } from 'lucide-react';
import type { FC } from 'react';

const SCOPE_LABELS: Record<RailScope, string> = {
  input: 'Input',
  output: 'Output',
  retrieval: 'Retrieval',
};

export interface RailsListProps {
  data: RailsConfig;
  onChange: (next: RailsConfig) => void;
}

/**
 * The guardrails a config can run, each with a switch and its own settings.
 *
 * Rails are listed whether or not the config uses them, so turning one on is a single
 * click rather than a hunt — and the switch performs every edit the engine needs at once
 * (flow, prompt, and task model), which is what makes the coupling invisible here.
 *
 * The row owns only what every rail shares; everything past it is the rail's own.
 */
export const RailsList: FC<RailsListProps> = ({ data, onChange }) => (
  <Stack gap="0" role="list">
    {RAIL_DEFINITIONS.map((rail) => (
      <RailRow key={rail.id} rail={rail} data={data} onChange={onChange} />
    ))}
  </Stack>
);

interface RailRowProps extends RailsListProps {
  rail: RailDefinition;
}

const RailRow: FC<RailRowProps> = ({ rail, data, onChange }) => {
  // Derived, not declared: a rail is running exactly when one of its stages is. Deriving it
  // is what keeps the switch and the stage badges from ever contradicting each other.
  const enabled = rail.scopes.some((scope) => rail.isScopeEnabled(data, scope));
  // Offered only when switching off left settings behind, so the row stays quiet in the
  // common case and the action appears exactly when there is something to discard.
  const canDiscard = !enabled && rail.hasStoredSettings(data);

  return (
    // A grid, not nested Flex: the switch needs to center against the title row's own
    // height (driven by the tallest of the label, badges, and settings button), while the
    // description sits a full row below, column-aligned with the title rather than the
    // switch. A single flex row can't express "center with row 1, but only row 1" once a
    // second row is added underneath.
    <div
      role="listitem"
      className="border-border-subtle grid grid-cols-[auto_1fr] items-start gap-x-density-lg gap-y-density-xs border-b py-density-md last:border-b-0"
    >
      <Switch
        className="col-start-1 row-start-1 self-center"
        checked={enabled}
        onCheckedChange={(next) => onChange(rail.setEnabled(data, next))}
        attributes={{ SwitchInput: { 'aria-label': rail.label } }}
      />

      <Flex align="center" justify="between" gap="density-lg" className="col-start-2 row-start-1">
        <Text kind="label/bold/md">{rail.label}</Text>

        {/*
          Right-aligned so the stage badges sit next to the settings gear rather than
          drifting toward the label — the two controls act together (badges show what the
          gear configures).

          Read-only: the switches that change this live in the rail's own settings.
        */}
        <Flex align="center" gap="density-md" wrap="wrap">
          {rail.scopes.map((scope) => {
            const scopeEnabled = rail.isScopeEnabled(data, scope);
            return (
              <Badge
                key={scope}
                kind="solid"
                color={scopeEnabled ? 'green' : 'gray'}
                // The visible text is the stage name either way, so the state is
                // colour-only without this.
                aria-label={`${SCOPE_LABELS[scope]} ${scopeEnabled ? 'enabled' : 'disabled'}`}
              >
                {SCOPE_LABELS[scope]}
              </Badge>
            );
          })}

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

          {rail.renderSettings?.({ data, onChange })}
        </Flex>
      </Flex>

      <Text
        kind="body/regular/sm"
        className="col-start-2 row-start-2 max-w-[560px] text-text-secondary"
      >
        {rail.description}
      </Text>
    </div>
  );
};
