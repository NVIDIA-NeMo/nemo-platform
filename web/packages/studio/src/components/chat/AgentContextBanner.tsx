// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button } from '@nvidia/foundations-react-core';
import { Bot } from 'lucide-react';
import type { FC } from 'react';

interface AgentContextBannerProps {
  agentName: string;
  baselineModelUrn: string | null;
  onApplyToAgent: () => void;
}

export const AgentContextBanner: FC<AgentContextBannerProps> = ({
  agentName,
  baselineModelUrn,
  onApplyToAgent,
}) => {
  return (
    <div className="mb-3 flex items-center gap-3 rounded-lg border border-accent bg-accent-blue-subtle px-3 py-2">
      <Bot size={18} className="shrink-0" />
      <div className="min-w-0 flex-1 text-sm">
        Testing models for agent <span className="font-semibold">{agentName}</span>.
        Panel 1 is locked to{' '}
        <span className="font-mono">{baselineModelUrn ?? '—'}</span> as Baseline.
      </div>
      <Button kind="primary" color="brand" size="small" onClick={onApplyToAgent}>
        Apply to Agent
      </Button>
    </div>
  );
};
