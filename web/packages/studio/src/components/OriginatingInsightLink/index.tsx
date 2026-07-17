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

/**
 * The Voyager artwork above an "Originating insight" label, both linking to the insight detail page.
 * Shared by the experiment group detail page and the experiment detail root-cause card.
 */
export const OriginatingInsightLink: FC<OriginatingInsightLinkProps> = ({ insightId }) => {
  const workspace = useWorkspaceFromPath();
  return (
    <Anchor asChild>
      <Link
        to={getOptimizerInsightRoute(workspace, insightId)}
        className="flex w-[90px] shrink-0 flex-col items-center gap-density-md text-center no-underline hover:!bg-transparent hover:underline"
      >
        <img src={voyagerArt} alt="" aria-hidden className="h-[78px] w-[90px]" />
        <Text kind="body/bold/md" color="brand" className="text-center">
          Originating
          <br />
          insight
        </Text>
      </Link>
    </Anchor>
  );
};
