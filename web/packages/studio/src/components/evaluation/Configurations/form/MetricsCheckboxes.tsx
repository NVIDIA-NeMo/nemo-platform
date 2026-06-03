// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { METRIC_NAMES_API, MetricNameApi, METRIC_LABELS } from '@nemo/common/src/constants/metrics';
import { Checkbox, FormField, Stack, TextInput } from '@nvidia/foundations-react-core';
import { LLMJudgeInput } from '@studio/components/evaluation/Configurations/form/LLMJudgeInput';
import { StringCheckInput } from '@studio/components/evaluation/Configurations/form/StringCheckInput';
import { CreateConfigFormData } from '@studio/hooks/evaluation/useCreateConfigurationForm';
import { type FC, type Ref } from 'react';
import { Controller, Path, useFormContext, useWatch } from 'react-hook-form';

interface MetricFieldConfig {
  name: Path<CreateConfigFormData>;
  label: string;
  info: string;
}

interface MetricConfigField {
  metric: MetricNameApi;
  fields: MetricFieldConfig[];
}

const METRIC_CONFIG_FIELDS: MetricConfigField[] = [
  {
    metric: 'bleu',
    fields: [
      {
        name: 'configData.metricConfigs.bleu.references',
        label: 'BLEU References',
        info: 'Reference text to compare against for BLEU score calculation',
      },
      {
        name: 'configData.metricConfigs.bleu.candidate',
        label: 'Candidate',
        info: 'The candidate text to evaluate',
      },
    ],
  },
  {
    metric: 'rouge',
    fields: [
      {
        name: 'configData.metricConfigs.rouge.groundTruth',
        label: 'ROUGE Ground Truth',
        info: 'Reference text to compare against output from evaluation inference',
      },
      {
        name: 'configData.metricConfigs.rouge.prediction',
        label: 'Prediction Reference',
        info: 'Reference to the prediction field in the dataset',
      },
    ],
  },
  {
    metric: 'em',
    fields: [
      {
        name: 'configData.metricConfigs.em.groundTruth',
        label: 'Exact Match Ground Truth',
        info: 'Reference text to compare against output from evaluation inference',
      },
      {
        name: 'configData.metricConfigs.em.prediction',
        label: 'Prediction Reference',
        info: 'Reference to the prediction field in the dataset',
      },
    ],
  },
  {
    metric: 'f1',
    fields: [
      {
        name: 'configData.metricConfigs.f1.groundTruth',
        label: 'F1 Ground Truth',
        info: 'Reference text to compare against output from evaluation inference',
      },
      {
        name: 'configData.metricConfigs.f1.prediction',
        label: 'Prediction Reference',
        info: 'Reference to the prediction field in the dataset',
      },
    ],
  },
];

interface MetricConfigFieldProps {
  fieldConfig: MetricFieldConfig;
  disabled?: boolean;
}

const MetricConfigFieldComponent: FC<MetricConfigFieldProps> = ({ fieldConfig, disabled }) => {
  const { control } = useFormContext<CreateConfigFormData>();

  return (
    <Controller
      name={fieldConfig.name}
      control={control}
      render={({ field, fieldState }) => (
        <FormField
          slotLabel={fieldConfig.label}
          slotInfo={fieldConfig.info}
          slotError={fieldState.error?.message}
          status={fieldState.error ? 'error' : undefined}
        >
          {({ status, ...args }) => (
            <TextInput
              status={status}
              disabled={disabled}
              value={(field.value as string) || ''}
              onChange={field.onChange}
              onBlur={field.onBlur}
              attributes={{ Input: args }}
            />
          )}
        </FormField>
      )}
    />
  );
};

export interface MetricsCheckboxesProps {
  disabled?: boolean;
  showMetricConfigFields?: boolean;
}

export const MetricsCheckboxes: FC<MetricsCheckboxesProps> = ({
  disabled,
  showMetricConfigFields = true,
}) => {
  const {
    control,
    formState: { errors },
  } = useFormContext<CreateConfigFormData>();

  const metrics = useWatch({
    control,
    name: 'configData.metrics',
  });

  return (
    <FormField
      slotError={errors?.configData?.metrics?.message}
      status={errors?.configData?.metrics ? 'error' : undefined}
    >
      {() => (
        <Stack gap="density-2xl" className="w-full">
          {METRIC_NAMES_API.map((metric) => {
            const isSelected = metrics?.includes(metric);

            return (
              <Stack key={metric} gap="density-2xl">
                <Controller
                  name="configData.metrics"
                  control={control}
                  disabled={disabled}
                  render={({ field }) => (
                    <MetricOption
                      {...field}
                      value={field.value}
                      label={metric}
                      onChange={field.onChange}
                    />
                  )}
                />

                {/* Interleaved input fields based on metric type */}
                {isSelected &&
                  (showMetricConfigFields ||
                    metric === 'llm-judge' ||
                    metric === 'string-check') && (
                    <>
                      {metric === 'llm-judge' ? (
                        <LLMJudgeInput />
                      ) : metric === 'string-check' ? (
                        <StringCheckInput operatorLabel="" disabled={disabled} />
                      ) : (
                        showMetricConfigFields &&
                        METRIC_CONFIG_FIELDS.find((config) => config.metric === metric)?.fields.map(
                          (fieldConfig) => (
                            <MetricConfigFieldComponent
                              key={fieldConfig.name}
                              fieldConfig={fieldConfig}
                              disabled={disabled}
                            />
                          )
                        )
                      )}
                    </>
                  )}
              </Stack>
            );
          })}
        </Stack>
      )}
    </FormField>
  );
};

type MetricOptionProps = {
  label: MetricNameApi;
  value?: MetricNameApi[];
  disabled?: boolean;
  onChange: (value: MetricNameApi[]) => void;
  ref?: Ref<HTMLInputElement>;
};

export const MetricOption = ({
  label,
  value = [],
  disabled = false,
  onChange,
  ref,
}: MetricOptionProps) => {
  const handleCheckClick = () => {
    if (disabled) return;
    const isSelected = value.includes(label);
    onChange(isSelected ? value.filter((m) => m !== label) : [...value, label]);
  };

  return (
    <Checkbox
      attributes={{
        CheckboxInput: { id: `metric-checkbox-${label}`, 'aria-label': METRIC_LABELS[label] },
        Label: { htmlFor: `metric-checkbox-${label}` },
      }}
      ref={ref}
      disabled={disabled}
      checked={value.includes(label)}
      slotLabel={METRIC_LABELS[label]}
      onCheckedChange={handleCheckClick}
    />
  );
};
