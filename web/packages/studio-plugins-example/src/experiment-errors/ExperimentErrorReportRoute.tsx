// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { ExperimentErrorSpansTable } from '@nemo/studio-plugins-example/experiment-errors/ExperimentErrorSpansTable';
import { ExperimentErrorSummaryTable } from '@nemo/studio-plugins-example/experiment-errors/ExperimentErrorSummaryTable';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  getExperimentDetailRoute,
  getExperimentGroupDetailRoute,
  getExperimentRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC } from 'react';

/**
 * Error report page contributed by the `experiment-errors` plugin via its `routes` manifest. Sits
 * under the single-experiment detail route; the detail-page banner links here. Composes the two
 * query-plugin-backed tables: errors grouped by type on top, the individual error spans below.
 */
export const ExperimentErrorReportRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { experimentGroupName, experimentName } = useRequiredPathParams([
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.experimentName,
  ]);

  useBreadcrumbs({
    items: [
      { href: getExperimentRoute(workspace), slotLabel: 'Experiments' },
      {
        href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
        slotLabel: experimentGroupName,
      },
      {
        href: getExperimentDetailRoute(workspace, experimentGroupName, experimentName),
        slotLabel: experimentName,
      },
      { slotLabel: 'Error report' },
    ],
  });

  return (
    <AccessibleTitle title={`${experimentName} — Error report`}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Error report"
          slotDescription={`Error spans across the "${experimentName}" experiment.`}
        />
        <ExperimentErrorSummaryTable workspace={workspace} experimentName={experimentName} />
        <ExperimentErrorSpansTable workspace={workspace} experimentName={experimentName} />
      </Stack>
    </AccessibleTitle>
  );
};
