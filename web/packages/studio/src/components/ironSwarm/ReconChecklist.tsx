// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { ReconStep } from '@studio/components/ironSwarm/swarm/swarmModel';
import { Check, Loader2 } from 'lucide-react';
import { FC } from 'react';

interface ReconChecklistProps {
  steps: ReconStep[];
  busy?: boolean;
  activity?: string; // live label for the in-flight stage; falls back to a generic "Working…"
}

// The benign-suite recon steps as a checklist. iron-swarm emits one event per finished recon node, so every
// received step is complete; a trailing spinner shows while more work is still in flight.
export const ReconChecklist: FC<ReconChecklistProps> = ({ steps, busy, activity }) => {
  if (steps.length === 0 && !busy) return null;
  return (
    <Stack gap="2">
      <Text kind="body/semibold/sm" className="uppercase tracking-wide text-gray-400">
        Recon
      </Text>
      {steps.map((step) => (
        <Flex key={step.phase} gap="density-sm" align="center">
          <Check size={16} className="text-green-400" />
          <Text kind="body/regular/sm">{step.label}</Text>
        </Flex>
      ))}
      {busy ? (
        <Flex gap="density-sm" align="center">
          <Loader2 size={16} className="animate-spin text-gray-400" />
          <Text kind="body/regular/sm" className="text-gray-400">
            {activity ?? 'Working…'}
          </Text>
        </Flex>
      ) : null}
    </Stack>
  );
};
