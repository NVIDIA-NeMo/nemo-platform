// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Gauge, Hash, Timer } from 'lucide-react';
import type { FC } from 'react';

export interface ChatMetrics {
  ttftMs: number;
  totalMs: number;
  completionTokens: number;
  tokensPerSec: number;
}

interface StatsBadgeProps {
  metrics: ChatMetrics;
}

export const StatsBadge: FC<StatsBadgeProps> = ({ metrics }) => {
  // NVIDIA brand green via the Kaizen `--color-brand` token — these metrics
  // are a positive signal (faster, more tokens) so they should pop. No border,
  // no background — reads as inline text below the assistant message.
  return (
    <div className="inline-flex items-center gap-4 text-xs font-mono text-[var(--color-brand)]">
      <span className="inline-flex items-center gap-1" title="Time to first token">
        <Timer size={12} />
        {metrics.ttftMs}ms
      </span>
      <span className="inline-flex items-center gap-1" title="Tokens per second">
        <Gauge size={12} />
        {metrics.tokensPerSec.toFixed(1)} t/s
      </span>
      <span className="inline-flex items-center gap-1" title="Completion tokens">
        <Hash size={12} />
        {metrics.completionTokens} tokens
      </span>
    </div>
  );
};
