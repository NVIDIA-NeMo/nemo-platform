// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack } from '@nvidia/foundations-react-core';
import { GuardrailConfigurationPanel } from '@studio/routes/guardrails/GuardrailConfigTab/GuardrailConfigurationPanel';
import { RawConfigSection } from '@studio/routes/guardrails/GuardrailConfigTab/RawConfigSection';
import { useDraftRailsConfig } from '@studio/routes/guardrails/GuardrailForm/useDraftRailsConfig';
import type { FC } from 'react';

/**
 * The Configuration tab: the rails a guardrail runs, and the document they produce.
 *
 * Editing happens entirely in the panel above; the JSON below is the read-only result, so
 * the effect of switching a rail on — the flow and the prompt it writes together — is
 * visible without leaving the page.
 *
 * The draft comes from the shared hook the checks tab also uses, so a run against Draft
 * exercises exactly the document rendered here.
 */
export const GuardrailConfigTab: FC = () => {
  const { draftConfig } = useDraftRailsConfig();

  return (
    <Stack className="gap-density-2xl">
      <GuardrailConfigurationPanel />
      <RawConfigSection data={draftConfig} />
    </Stack>
  );
};
