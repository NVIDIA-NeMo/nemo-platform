// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { ENTITY_NAME_HELP, entityNameSchema } from '@nemo/common/src/utils/entityName';
import { useGuardrailsCreateConfig } from '@nemo/sdk/generated/platform/api';
import type { GuardrailConfig } from '@nemo/sdk/generated/platform/schema';
import { getErrorMessage } from '@studio/api/common/utils';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getGuardrailDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const createGuardrailFormSchema = z.object({
  name: entityNameSchema(),
});

type FormData = z.infer<typeof createGuardrailFormSchema>;

interface Props {
  open: boolean;
  onClose: () => void;
}

export const CreateGuardrailModal: FC<Props> = ({ open, onClose }) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    control,
    handleSubmit,
    reset,
    formState: { isValid },
  } = useForm<FormData>({
    resolver: zodResolver(createGuardrailFormSchema),
    defaultValues: { name: '' },
    mode: 'onChange',
  });

  const {
    mutateAsync: createConfig,
    isPending,
    error,
    reset: resetMutation,
  } = useGuardrailsCreateConfig();

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    // setTimeout 0 lets the dialog's built-in focus management run first (it would otherwise
    // focus the slotInfo icon button, which appears before the input in DOM order).
    const id = setTimeout(() => {
      containerRef.current?.querySelector<HTMLInputElement>('input')?.focus();
    }, 0);
    return () => clearTimeout(id);
  }, [open]);

  const handleClose = () => {
    reset();
    resetMutation();
    onClose();
  };

  const onSubmit = async (data: FormData) => {
    let config: GuardrailConfig;
    try {
      config = await createConfig({ workspace, data: { name: data.name } });
    } catch {
      // The modal stays open and surfaces the failure via `errorText` below.
      return;
    }
    await queryClient.invalidateQueries({
      queryKey: [`/apis/guardrails/v2/workspaces/${workspace}/configs`],
    });
    handleClose();
    navigate(getGuardrailDetailRoute(workspace, config.name ?? data.name));
  };

  return (
    <FormModal
      open={open}
      title="Create Guardrail"
      submitButtonText="Create"
      disabled={isPending}
      loading={isPending}
      submitDisabled={!isValid}
      errorText={error ? getErrorMessage(error) : null}
      onSubmit={handleSubmit(onSubmit)}
      onClose={handleClose}
    >
      <div ref={containerRef}>
        <ControlledTextInput
          label="Name"
          disabled={isPending}
          useControllerProps={{ name: 'name', control }}
          formFieldProps={{ slotInfo: ENTITY_NAME_HELP }}
          attributes={{
            Input: {
              autoComplete: 'off',
              autoCapitalize: 'none',
              autoCorrect: 'off',
              spellCheck: false,
            },
          }}
        />
      </div>
    </FormModal>
  );
};
