// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { Pre } from '@studio/components/common/Pre';
import { FC } from 'react';

export interface MetricDisplayProps {
  metricName: string;
  metricConfig: {
    type: string;
    params?: Record<string, unknown>;
  };
}

/**
 * Component to display individual metric details.
 * Handles different metric types: string-check, bleu, rouge, em, f1.
 *
 * @param props.metricName - User-defined name for the metric (the key in the metrics object)
 * @param props.metricConfig - Metric configuration containing type and params
 */
export const MetricDisplay: FC<MetricDisplayProps> = ({ metricName, metricConfig }) => {
  const params = metricConfig.params || {};
  const type = metricConfig.type?.toLowerCase() || '';

  return (
    <Stack gap="density-sm">
      <Text kind="label/bold/md">{metricName}</Text>
      <KVPair label="Type" value={metricConfig.type} />

      {type === 'string-check' && (
        <KVPair
          label="Check Pattern"
          value={
            params.check != null
              ? Array.isArray(params.check)
                ? params.check.join(',')
                : String(params.check)
              : undefined
          }
        />
      )}

      {type === 'bleu' && (
        <>
          <KVPair
            label="References"
            value={params.references != null ? <Pre>{String(params.references)}</Pre> : undefined}
          />
          {params.candidate != null && (
            <KVPair label="Candidate" value={<Pre>{String(params.candidate)}</Pre>} />
          )}
        </>
      )}

      {type === 'rouge' && (
        <>
          <KVPair
            label="Ground Truth Reference"
            value={
              params.ground_truth != null ? <Pre>{String(params.ground_truth)}</Pre> : undefined
            }
          />
          {params.prediction != null && (
            <KVPair label="Prediction" value={<Pre>{String(params.prediction)}</Pre>} />
          )}
        </>
      )}

      {type === 'em' && (
        <>
          <KVPair
            label="Ground Truth Reference"
            value={
              params.ground_truth != null ? <Pre>{String(params.ground_truth)}</Pre> : undefined
            }
          />
          {params.prediction != null && (
            <KVPair label="Prediction" value={<Pre>{String(params.prediction)}</Pre>} />
          )}
        </>
      )}

      {type === 'f1' && (
        <>
          <KVPair
            label="Ground Truth Reference"
            value={
              params.ground_truth != null ? <Pre>{String(params.ground_truth)}</Pre> : undefined
            }
          />
          {params.prediction != null && (
            <KVPair label="Prediction" value={<Pre>{String(params.prediction)}</Pre>} />
          )}
        </>
      )}
    </Stack>
  );
};
