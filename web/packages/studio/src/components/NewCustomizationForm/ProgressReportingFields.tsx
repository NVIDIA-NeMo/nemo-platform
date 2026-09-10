// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSliderWithTextInput } from '@nemo/common/src/components/form/ControlledSliderWithTextInput';
import { ControlledStringListInput } from '@studio/components/NewCustomizationForm/ControlledStringListInput';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { specSliderProps } from '@studio/util/forms/specDefaults';
import { useFormContext, type FieldPath } from 'react-hook-form';

interface ProgressReportingFieldsProps {
  /** Path of the `progress_reporting` object, e.g. `automodel.schedule.progress_reporting`. */
  prefix: string;
  /** Flattened spec table for the backend, and the key its `progress_reporting` sits under. */
  defaults: ReadonlyMap<string, unknown>;
  defaultsPrefix: string;
  disabled: boolean;
}

/**
 * The shared `ProgressReportingConfig`, which every backend carries but hangs off a
 * different parent — `schedule` on automodel and unsloth, `training` on RL.
 *
 * `time_series_metrics` decides which metrics are recorded at all, so leaving it unbound
 * meant the job details charts could only ever show whatever the backend chose by default.
 */
export const ProgressReportingFields = ({
  prefix,
  defaults,
  defaultsPrefix,
  disabled,
}: ProgressReportingFieldsProps) => {
  const { control } = useFormContext<CustomizationFormFields>();
  const field = (name: string) => `${prefix}.${name}` as FieldPath<CustomizationFormFields>;

  return (
    <>
      <ControlledSliderWithTextInput
        useControllerProps={{ name: field('min_report_interval_seconds'), control }}
        formFieldProps={{
          slotLabel: 'Min Report Interval (s)',
          slotInfo: 'Floor on how often progress is reported, to keep long runs from flooding.',
        }}
        {...specSliderProps(defaults, `${defaultsPrefix}_min_report_interval_seconds`)}
        min={1}
        max={600}
        step={1}
        disabled={disabled}
      />
      <ControlledStringListInput
        useControllerProps={{ name: field('time_series_metrics'), control }}
        formFieldProps={{
          slotLabel: 'Time Series Metrics',
          slotInfo:
            'Comma separated metric names to record over time. Left unset, the backend picks its own set.',
        }}
        placeholder="train_loss, val_loss"
        disabled={disabled}
      />
    </>
  );
};
