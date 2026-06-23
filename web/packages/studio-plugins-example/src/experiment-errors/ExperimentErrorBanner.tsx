// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryPlugin } from '@nemo/studio-plugins-example/queryPlugin/useQueryPlugin';
import { Banner, Button } from '@nvidia/foundations-react-core';
import { getExperimentErrorReportRoute } from '@nemo/studio-plugins-example/experiment-errors/routePath';
import type { ExperimentErrorSummary } from '@nemo/studio-plugins-example/experiment-errors/types';
import type { SlotContextMap } from '@studio/plugins/types';
import { type FC } from 'react';
import { useNavigate } from 'react-router-dom';

type Props = SlotContextMap['experiments.detail.beforeSearch'];

/**
 * Slot banner summarizing error spans across the whole experiment, with a link to the full error
 * report page. Backed by the `experiment-error-summary` query plugin (same total the report's
 * by-type table sums to), so the count reflects every session, not just the loaded test-case page.
 *
 * Renders nothing while loading, when the query plugin is unavailable, or when the experiment has
 * no error spans — so a clean experiment shows no banner at all.
 */
export const ExperimentErrorBanner: FC<Props> = ({
  workspace,
  experimentGroupName,
  experimentName,
}) => {
  const navigate = useNavigate();
  const { data: result, isLoading, error } = useQueryPlugin<ExperimentErrorSummary>(
    workspace,
    'experiment-error-summary',
    { experiment_id: experimentName },
  );

  const data = result?.data;
  const totalErrorSpans = data?.total_error_spans ?? 0;
  if (isLoading || error || totalErrorSpans === 0) return null;

  const errorTypeCount = data?.rows?.length ?? 0;

  return (
    <Banner
      kind="inline"
      status="error"
      slotActions={
        <Button
          kind="secondary"
          onClick={() =>
            navigate(getExperimentErrorReportRoute(workspace, experimentGroupName, experimentName))
          }
        >
          View error report
        </Button>
      }
    >
      {totalErrorSpans.toLocaleString()} error span{totalErrorSpans === 1 ? '' : 's'} across{' '}
      {errorTypeCount} error type{errorTypeCount === 1 ? '' : 's'} in this experiment.
    </Banner>
  );
};
