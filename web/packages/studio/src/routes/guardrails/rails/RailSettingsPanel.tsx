// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, SidePanel, Stack, Text } from '@nvidia/foundations-react-core';
import type { RailDefinition } from '@studio/routes/guardrails/rails/types';
import { type FC, useEffect, useState } from 'react';

export interface RailSettingsPanelProps {
  /** The rail being configured, or null when the panel is closed. */
  rail: RailDefinition | null;
  /** The saved working copy the draft branches from. */
  data: RailsConfig;
  onApply: (next: RailsConfig) => void;
  onClose: () => void;
}

/**
 * Shared shell for a rail's settings.
 *
 * Edits go into a local draft rather than straight into the form, so the panel's two exits
 * mean different things: Save applies the draft, closing discards it. Without that, the X
 * would silently keep changes the user was backing out of.
 *
 * Applying only updates the guardrail's working copy — nothing reaches the server until
 * the page's Save Guardrail.
 */
export const RailSettingsPanel: FC<RailSettingsPanelProps> = ({ rail, data, onApply, onClose }) => {
  const [draft, setDraft] = useState<RailsConfig>(data);

  // Re-seed whenever a panel opens, so it always starts from the current working copy
  // rather than whatever the previous rail left behind.
  useEffect(() => {
    if (rail) setDraft(data);
    // `data` is intentionally excluded: re-seeding on every keystroke elsewhere would
    // throw away the draft mid-edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rail]);

  const RailPanel = rail?.Panel;

  return (
    <SidePanel
      className="w-[min(560px,90vw)]"
      bordered
      modal={false}
      open={Boolean(rail)}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      slotHeading={<Text kind="label/bold/lg">{rail ? `${rail.label} Rail` : ''}</Text>}
      slotFooter={
        <Flex justify="end" gap="density-sm" className="w-full">
          <Button kind="secondary" color="neutral" onClick={onClose}>
            Cancel
          </Button>
          <Button
            color="brand"
            onClick={() => {
              onApply(draft);
              onClose();
            }}
          >
            Save
          </Button>
        </Flex>
      }
    >
      {rail && RailPanel ? (
        <Stack gap="density-lg">
          <Text kind="body/regular/sm" className="text-text-secondary">
            {rail.description}
          </Text>
          <RailPanel data={draft} onChange={setDraft} />
        </Stack>
      ) : null}
    </SidePanel>
  );
};
