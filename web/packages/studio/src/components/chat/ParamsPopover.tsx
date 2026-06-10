// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { InferenceParamsSliders } from '@nemo/common/src/components/InferenceParamsSliders';
import { Button, Popover } from '@nvidia/foundations-react-core';
import type { InferenceParams } from '@studio/components/chat/params';
import { Sliders } from 'lucide-react';
import { useState, type FC } from 'react';

interface ParamsPopoverProps {
  value: InferenceParams;
  onChange: (next: InferenceParams) => void;
  /** When true, shows a labeled "Params" button instead of icon-only. */
  showLabel?: boolean;
}

export const ParamsPopover: FC<ParamsPopoverProps> = ({ value, onChange, showLabel }) => {
  const [open, setOpen] = useState(false);

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      slotContent={<InferenceParamsSliders value={value} onChange={onChange} />}
    >
      <Button
        kind="secondary"
        size="small"
        aria-label="Inference parameters"
        title="Inference parameters"
      >
        <Sliders size={14} />
        {showLabel ? 'Params' : null}
      </Button>
    </Popover>
  );
};
