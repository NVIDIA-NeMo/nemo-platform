// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Block, Stack, Text } from '@nvidia/foundations-react-core';
import { Globe } from 'lucide-react';
import type { FC, ReactNode } from 'react';

/** Shared heading for external-agent empty states, so the phrasing lives in one place. */
export const EXTERNAL_AGENT_HEADING = 'This agent runs outside NeMo Platform';

/** Centered notice used where an external agent has no NMP-managed surface (e.g. Logs). */
export const ExternalAgentNotice: FC<{ detail: ReactNode }> = ({ detail }) => (
  <Block padding="4">
    <Stack gap="2" align="center" className="pt-8 text-center">
      <Globe className="size-8 text-subtle" />
      <Text kind="body/semibold/md">{EXTERNAL_AGENT_HEADING}</Text>
      <Text kind="body/regular/sm" color="secondary">
        {detail}
      </Text>
    </Stack>
  </Block>
);
