// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { Button, Flex } from '@nvidia/foundations-react-core';
import type { GuardrailFormValues } from '@studio/routes/guardrails/GuardrailForm/formModel';
import { useGuardrailForm } from '@studio/routes/guardrails/GuardrailForm/useGuardrailForm';
import type { FC } from 'react';
import { useFormContext } from 'react-hook-form';

/**
 * Detail-header actions: Reset (discard) and Save. When the form is pristine the
 * buttons stay mounted but hidden (`visibility: hidden` + `aria-hidden`) so the
 * header row always reserves their height and content below it never shifts.
 */
export const GuardrailHeaderActions: FC = () => {
  const {
    formState: { isDirty },
  } = useFormContext<GuardrailFormValues>();
  const { save, isSaving, resetToServer } = useGuardrailForm();

  return (
    <Flex
      gap="density-sm"
      className={isDirty ? undefined : 'invisible pointer-events-none'}
      aria-hidden={!isDirty}
    >
      <Button kind="secondary" color="neutral" onClick={resetToServer} disabled={isSaving}>
        Reset
      </Button>
      <LoadingButton color="brand" onClick={() => save()} loading={isSaving} disabled={isSaving}>
        Save Guardrail
      </LoadingButton>
    </Flex>
  );
};
