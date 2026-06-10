// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Block,
  Button,
  Flex,
  Slider,
  Stack,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { RotateCcw } from 'lucide-react';
import type { FC } from 'react';

export interface InferenceParamsSliderValues {
  temperature: number;
  top_p: number;
  top_k: number;
  max_tokens: number;
}

export const DEFAULT_INFERENCE_PARAMS: InferenceParamsSliderValues = {
  temperature: 0.7,
  top_p: 0.95,
  top_k: 40,
  max_tokens: 512,
};

const SLIDERS: Array<{
  key: keyof InferenceParamsSliderValues;
  label: string;
  min: number;
  max: number;
  step: number;
}> = [
  { key: 'temperature', label: 'temperature', min: 0, max: 2, step: 0.05 },
  { key: 'top_p', label: 'top_p', min: 0, max: 1, step: 0.01 },
  { key: 'top_k', label: 'top_k', min: 1, max: 100, step: 1 },
  { key: 'max_tokens', label: 'max_tokens', min: 32, max: 4096, step: 32 },
];

const formatValue = (value: number, step: number): string =>
  Number.isInteger(step) ? value.toString() : value.toFixed(2);

export interface InferenceParamsSlidersProps {
  value: InferenceParamsSliderValues;
  onChange: (next: InferenceParamsSliderValues) => void;
  disabled?: boolean;
  defaults?: InferenceParamsSliderValues;
}

interface ParamSliderRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  defaultValue: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}

const ParamSliderRow: FC<ParamSliderRowProps> = ({
  label,
  value,
  min,
  max,
  step,
  defaultValue,
  disabled,
  onChange,
}) => {
  const clamp = (v: number) => Math.min(Math.max(v, min), max);

  const handleSliderChange = (next: number) => {
    onChange(clamp(next));
  };

  const handleTextInputChange = (raw: string) => {
    if (raw === '') return;
    const parsed = parseFloat(raw);
    if (Number.isNaN(parsed)) return;
    onChange(clamp(parsed));
  };

  const handleReset = () => {
    onChange(defaultValue);
  };

  return (
    <Stack gap="density-xs" align="start" className="w-full">
      <Text kind="label/bold/sm">{label}</Text>
      <Flex align="center" gap="density-sm" className="w-full">
        <Block className="min-w-0 flex-1">
          <Slider
            value={value}
            onValueChange={handleSliderChange}
            min={min}
            max={max}
            step={step}
            aria-label={label}
            disabled={disabled}
          />
        </Block>
        <TextInput
          aria-label={`${label} value`}
          value={formatValue(value, step)}
          max={max.toString()}
          min={min.toString()}
          step={step.toString()}
          type="number"
          disabled={disabled}
          className="h-[40px] w-[72px] shrink-0"
          onValueChange={handleTextInputChange}
          attributes={{
            Input: {
              'aria-label': `${label}_text_input`,
              className: 'text-center',
            },
          }}
        />
        <Button
          kind="tertiary"
          size="small"
          aria-label={`Reset ${label} to default value`}
          disabled={disabled}
          onClick={handleReset}
          className="shrink-0"
          type="button"
        >
          <RotateCcw size={16} />
        </Button>
      </Flex>
    </Stack>
  );
};

export const InferenceParamsSliders: FC<InferenceParamsSlidersProps> = ({
  value,
  onChange,
  disabled,
  defaults = DEFAULT_INFERENCE_PARAMS,
}) => {
  const update = (key: keyof InferenceParamsSliderValues, v: number) => {
    onChange({ ...value, [key]: v });
  };

  return (
    <Stack align="start" className="w-[400px] p-4">
      <Text kind="label/semibold/md" className="mb-density-xl text-[var(--text-color-secondary)]">
        Inference Params
      </Text>
      <Stack gap="density-lg" className="w-full">
        {SLIDERS.map((s) => (
          <ParamSliderRow
            key={s.key}
            label={s.label}
            value={value[s.key]}
            min={s.min}
            max={s.max}
            step={s.step}
            defaultValue={defaults[s.key]}
            disabled={disabled}
            onChange={(v) => update(s.key, v)}
          />
        ))}
      </Stack>
    </Stack>
  );
};
