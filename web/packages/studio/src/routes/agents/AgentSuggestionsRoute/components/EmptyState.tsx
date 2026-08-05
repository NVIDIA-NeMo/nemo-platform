// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { Button } from '@nvidia/foundations-react-core';
import { getAgentsListRoute } from '@studio/routes/utils';
import { Lightbulb } from 'lucide-react';
import { type FC } from 'react';
import { Link } from 'react-router';

export const EmptyState: FC = () => (
  <ErrorMessage
    slotMedia={<Lightbulb className="size-16" />}
    header="No optimization suggestions yet"
    message="Run the agent optimizer to generate suggestions for improving your deployments."
  />
);

export const NoAgentsEmptyState: FC<{ workspace: string }> = ({ workspace }) => (
  <ErrorMessage
    slotMedia={<Lightbulb className="size-16" />}
    header="No agents yet"
    message="Create an agent before running the optimizer — there's nothing to analyze yet."
    slotFooter={
      <Button kind="secondary" asChild>
        <Link to={getAgentsListRoute(workspace)}>Go to Agents</Link>
      </Button>
    }
  />
);
