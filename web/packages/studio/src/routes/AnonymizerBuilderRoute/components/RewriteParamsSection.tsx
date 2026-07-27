// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledCheckbox } from '@nemo/common/src/components/form/ControlledCheckbox';
import { ControlledSegmentedControl } from '@nemo/common/src/components/form/ControlledSegmentedControl';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormField, Slider, Stack } from '@nvidia/foundations-react-core';
import {
  PRIVACY_GOAL_MODE_CUSTOM,
  PRIVACY_GOAL_MODE_OPTIONS,
  REWRITE_MIN_MAX_REPAIR_ROUNDS,
  RISK_TOLERANCE_LABELS,
  RISK_TOLERANCE_ORDER,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { FC } from 'react';
import { useController, useFormContext, useWatch } from 'react-hook-form';

export const RewriteParamsSection: FC = () => {
  const { control } = useFormContext<AnonymizerFormData>();
  const privacyGoalMode = useWatch({ control, name: 'privacyGoalMode' });
  const {
    field: { onChange: onRiskToleranceChange, value: riskTolerance },
  } = useController({ control, name: 'riskTolerance' });

  return (
    <Stack gap="density-lg">
      <FormField slotLabel="Privacy Goal">
        <ControlledSegmentedControl
          className="w-full"
          size="tiny"
          items={PRIVACY_GOAL_MODE_OPTIONS}
          useControllerProps={{ name: 'privacyGoalMode', control }}
        />
      </FormField>
      {privacyGoalMode === PRIVACY_GOAL_MODE_CUSTOM && (
        <>
          <ControlledTextArea
            useControllerProps={{ name: 'privacyProtect', control }}
            formFieldProps={{
              slotLabel: 'Protect',
              slotInfo: 'What to protect, such as direct and quasi-identifiers.',
            }}
          />
          <ControlledTextArea
            useControllerProps={{ name: 'privacyPreserve', control }}
            formFieldProps={{
              slotLabel: 'Preserve',
              slotInfo: 'What to keep intact, such as utility and semantic meaning.',
            }}
          />
        </>
      )}
      <ControlledTextArea
        useControllerProps={{ name: 'rewriteInstructions', control }}
        formFieldProps={{ slotLabel: 'LLM Instructions' }}
      />
      {/* end tick labels overhang the track, so inset it to keep them inside the scroll box */}
      <FormField slotLabel="Risk Tolerance">
        <Slider
          aria-label="Risk tolerance"
          className="mb-5 px-6"
          orientation="horizontal"
          stepPosition="end"
          min={0}
          max={RISK_TOLERANCE_ORDER.length - 1}
          step={1}
          stepFormatFn={(index) => RISK_TOLERANCE_LABELS[RISK_TOLERANCE_ORDER[index]]}
          value={RISK_TOLERANCE_ORDER.indexOf(riskTolerance)}
          onValueChange={(index) => onRiskToleranceChange(RISK_TOLERANCE_ORDER[index])}
        />
      </FormField>
      <ControlledTextInput
        type="number"
        min={REWRITE_MIN_MAX_REPAIR_ROUNDS}
        useControllerProps={{ name: 'maxRepairRounds', control }}
        formFieldProps={{
          slotLabel: 'Max Repair Rounds',
          slotInfo: 'Repair passes run when leakage exceeds the tolerance. Set to 0 to disable.',
        }}
      />
      <ControlledCheckbox
        slotLabel="Strict Entity Protection. Forces every detected entity to be protected regardless of risk. No entity can be left unchanged."
        useControllerProps={{ name: 'strictEntityProtection', control }}
      />
    </Stack>
  );
};
