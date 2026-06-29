// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SpanKind } from '@nemo/sdk/generated/platform/schema';
import { Badge } from '@nvidia/foundations-react-core';
import { getSpanKindConfig } from '@studio/components/SpanKindBadge/spanKindConfig';
import type { FC } from 'react';

export interface SpanKindBadgeProps {
  kind: SpanKind | string | undefined;
}

// Outline badges color their text/border by `color`, but the icon otherwise
// falls back to the muted default — tint it to match the badge's accent.
const BADGE_ICON_CLASS: Record<string, string> = {
  teal: 'text-[color:var(--text-color-accent-teal)]',
  purple: 'text-[color:var(--text-color-accent-purple)]',
  blue: 'text-[color:var(--text-color-accent-blue)]',
  green: 'text-[color:var(--text-color-accent-green)]',
  yellow: 'text-[color:var(--text-color-accent-yellow)]',
  red: 'text-[color:var(--text-color-accent-red)]',
};

/** Outline badge identifying a span's kind (Agent, LLM, Tool, …). */
export const SpanKindBadge: FC<SpanKindBadgeProps> = ({ kind }) => {
  const config = getSpanKindConfig(kind);
  const Icon = config.icon;

  return (
    <Badge color={config.color} kind="outline">
      <Icon
        className={`size-3 shrink-0 ${BADGE_ICON_CLASS[config.color] ?? ''}`}
        role="img"
        aria-hidden
      />
      {config.label}
    </Badge>
  );
};
