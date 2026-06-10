// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Popover, Slider, Stack, Text } from '@nvidia/foundations-react-core';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { Sliders } from 'lucide-react';
import { useState, type FC } from 'react';

interface ParamsPopoverProps {
  value: InferenceParams;
  onChange: (next: InferenceParams) => void;
}

const SLIDERS: Array<{
  key: keyof InferenceParams;
  label: string;
  min: number;
  max: number;
  step: number;
  hint: string;
  default: number;
}> = [
  {
    key: 'temperature',
    label: 'Temperature',
    min: 0,
    max: 2,
    step: 0.05,
    hint: 'Randomness — higher = more creative.',
    default: DEFAULT_INFERENCE_PARAMS.temperature,
  },
  {
    key: 'top_p',
    label: 'Top P',
    min: 0,
    max: 1,
    step: 0.01,
    hint: 'Nucleus sampling cutoff.',
    default: DEFAULT_INFERENCE_PARAMS.top_p,
  },
  {
    key: 'top_k',
    label: 'Top K',
    min: 1,
    max: 100,
    step: 1,
    hint: 'Sample from top-K tokens. Provider-dependent.',
    default: DEFAULT_INFERENCE_PARAMS.top_k,
  },
  {
    key: 'max_tokens',
    label: 'Max tokens',
    min: 32,
    max: 4096,
    step: 32,
    hint: 'Hard cap on response length.',
    default: DEFAULT_INFERENCE_PARAMS.max_tokens,
  },
];

export const ParamsPopover: FC<ParamsPopoverProps> = ({ value, onChange }) => {
  const [open, setOpen] = useState(false);

  const update = (key: keyof InferenceParams, v: number) => {
    onChange({ ...value, [key]: v });
  };

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      slotContent={
        <Stack gap="density-lg" className="w-80 p-4">
          <div className="flex items-center justify-between">
            <Text kind="label/bold/sm">Inference parameters</Text>
            <Button kind="tertiary" size="small" onClick={() => onChange(DEFAULT_INFERENCE_PARAMS)}>
              Reset
            </Button>
          </div>
          {SLIDERS.map((s) => {
            const current = value[s.key];
            return (
              <Stack gap="density-xs" key={s.key}>
                <div className="flex items-baseline justify-between">
                  <Text kind="label/regular/sm">{s.label}</Text>
                  <Text kind="mono/sm" color="secondary">
                    {Number.isInteger(s.step) ? current : current.toFixed(2)}
                  </Text>
                </div>
                <Slider
                  value={current}
                  onValueChange={(v) => update(s.key, v)}
                  min={s.min}
                  max={s.max}
                  step={s.step}
                  aria-label={s.label}
                />
                <Text kind="label/regular/sm" color="secondary">
                  {s.hint}
                </Text>
              </Stack>
            );
          })}
        </Stack>
      }
    >
      <Button
        kind="secondary"
        size="small"
        aria-label="Inference parameters"
        title="Inference parameters"
      >
        <Sliders size={14} />
      </Button>
    </Popover>
  );
};
