// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Anchor, Text } from '@nvidia/foundations-react-core';
import voyagerArt from '@studio/assets/voyager.svg';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getOptimizerInsightRoute } from '@studio/routes/utils';
import { type FC } from 'react';
import { Link } from 'react-router-dom';

interface OriginatingInsightLinkProps {
  insightId: string;
}

/** Compact link (Voyager icon + label) to the insight that originated an experiment. */
export const OriginatingInsightLink: FC<OriginatingInsightLinkProps> = ({ insightId }) => {
  const workspace = useWorkspaceFromPath();
  return (
    <Anchor asChild>
      <Link
        to={getOptimizerInsightRoute(workspace, insightId)}
        className="inline-flex shrink-0 items-center gap-density-sm whitespace-nowrap no-underline hover:!bg-transparent hover:underline"
      >
        <img src={voyagerArt} alt="" aria-hidden className="h-5 w-5 object-contain" />
        <Text kind="body/bold/sm" color="brand">
          Originating insight
        </Text>
      </Link>
    </Anchor>
  );
};
