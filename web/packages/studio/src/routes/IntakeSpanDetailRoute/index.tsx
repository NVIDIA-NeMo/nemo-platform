// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeSpanDetailView } from '@studio/components/IntakeDetail/SpanDetailView';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type FC } from 'react';
import { useParams } from 'react-router-dom';

type SpanRouteParams = Record<typeof ROUTE_PARAMS.spanId, string | undefined>;

export const IntakeSpanDetailRoute: FC = () => {
  const { [ROUTE_PARAMS.spanId]: spanId } = useParams<SpanRouteParams>();
  const workspace = useWorkspaceFromPath();

  if (!spanId) {
    return <NotFound subheader="Span Not Found" message="The span route is missing a span ID." />;
  }

  return <IntakeSpanDetailView workspace={workspace} spanId={spanId} />;
};
