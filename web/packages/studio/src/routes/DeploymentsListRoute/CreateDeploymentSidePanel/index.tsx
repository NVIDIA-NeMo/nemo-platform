/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import type { ResourceRef } from '@nemo/common/src/types';
import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import {
  Button,
  Flex,
  SegmentedControl,
  SidePanel,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { AdvancedSettingsAccordion } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/AdvancedSettingsAccordion';
import { HuggingFaceSourceFields } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/HuggingFaceSourceFields';
import { NgcSourceFields } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/NgcSourceFields';
import {
  createDeploymentWizardSchema,
  defaultWizardValues,
  WORKSPACE_PICKER_FILESET,
  WORKSPACE_PICKER_MODEL,
  SOURCE_HF,
  SOURCE_WORKSPACE,
  SOURCE_NGC,
  type WizardFormValues,
} from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/schema';
import { useCreateDeploymentBySource } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/useCreateDeploymentBySource';
import { useHuggingFaceNameDefault } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/useHuggingFaceNameDefault';
import { WorkspaceSourceFields } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/WorkspaceSourceFields';
import { FC, useCallback, useEffect, useState } from 'react';
import { SubmitHandler, useForm } from 'react-hook-form';

/** Deep-link prefill: when set, opens the panel on the Workspace source with the given ref pre-selected. */
export interface CreateDeploymentPrefill {
  /** `<workspace>/<name>` reference to a model entity. Takes precedence over `fileset` when both are set. */
  modelRef?: ResourceRef;
  /** `<workspace>/<name>` reference to a fileset. */
  fileset?: ResourceRef;
}

export interface CreateDeploymentSidePanelProps {
  workspace: string;
  open: boolean;
  onClose: () => void;
  /** Pre-fill the Workspace source with a deep-linked model or fileset reference. */
  prefill?: CreateDeploymentPrefill;
}

function valuesFromPrefill(prefill: CreateDeploymentPrefill | undefined): WizardFormValues {
  const base = defaultWizardValues();
  if (!prefill) return base;
  if (prefill.modelRef) {
    return {
      ...base,
      source: SOURCE_WORKSPACE,
      workspacePickerType: WORKSPACE_PICKER_MODEL,
      modelRef: prefill.modelRef,
    };
  }
  if (prefill.fileset) {
    return {
      ...base,
      source: SOURCE_WORKSPACE,
      workspacePickerType: WORKSPACE_PICKER_FILESET,
      fileset: prefill.fileset,
    };
  }
  return base;
}

export const CreateDeploymentSidePanel: FC<CreateDeploymentSidePanelProps> = ({
  workspace,
  open,
  onClose,
  prefill,
}) => {
  const {
    createDeploymentFromWizard,
    isSubmitting,
    submitError,
    setSubmitError,
    statusMessage,
    clearStatusMessage,
  } = useCreateDeploymentBySource(workspace);
  const [advancedAccordion, setAdvancedAccordion] = useState<string>();

  const {
    control,
    handleSubmit,
    reset,
    getValues,
    setValue,
    watch,
    formState: { errors },
  } = useForm<WizardFormValues>({
    resolver: zodResolver(createDeploymentWizardSchema),
    defaultValues: defaultWizardValues(),
    mode: 'onChange',
    disabled: isSubmitting,
  });

  const source = watch('source');

  // On the HuggingFace source, default the name from the repo id until the user
  // types their own.
  useHuggingFaceNameDefault(control, setValue);

  useEffect(() => {
    if (open) {
      reset(valuesFromPrefill(prefill));
      setSubmitError(null);
      clearStatusMessage();
    }
  }, [clearStatusMessage, open, prefill, reset, setSubmitError]);

  const resetAndClose = useCallback(() => {
    reset(defaultWizardValues());
    setSubmitError(null);
    setAdvancedAccordion(undefined);
    onClose();
  }, [onClose, reset, setAdvancedAccordion, setSubmitError]);

  const onSubmit: SubmitHandler<WizardFormValues> = useCallback(
    (values) => createDeploymentFromWizard(values, resetAndClose),
    [createDeploymentFromWizard, resetAndClose]
  );

  const handleOpenChange = (next: boolean) => {
    if (!next && !isSubmitting) resetAndClose();
  };

  return (
    <SidePanel
      open={open}
      onOpenChange={handleOpenChange}
      side="right"
      bordered
      modal
      className="w-[600px] [&_.nv-side-panel-main]:gap-4"
      slotHeading="Create Deployment"
      renderContent={({ children }) => (
        <form className="flex min-h-0 flex-1 flex-col" onSubmit={handleSubmit(onSubmit)} noValidate>
          {children}
        </form>
      )}
      slotFooter={
        <Stack gap="2">
          {statusMessage ? (
            <Text kind="body/regular/sm" color="secondary" className="mr-auto max-w-full">
              {statusMessage}
            </Text>
          ) : null}
          {submitError ? (
            <Text kind="body/regular/sm" className="mr-auto max-w-full text-red-400">
              {submitError}
            </Text>
          ) : null}
          <Flex justify="end" gap="density-lg" className="w-full flex-wrap">
            <Button
              kind="tertiary"
              type="button"
              disabled={isSubmitting}
              onClick={() => {
                if (!isSubmitting) resetAndClose();
              }}
            >
              Cancel
            </Button>
            <LoadingButton type="submit" loading={isSubmitting} disabled={isSubmitting}>
              Deploy
            </LoadingButton>
          </Flex>
        </Stack>
      }
    >
      <Stack gap="density-xl" className="min-h-0 flex-1">
        <SegmentedControl
          className="w-full"
          value={source}
          onValueChange={(v) => {
            const keepName = getValues('name') || generateDefaultName();
            reset({
              ...defaultWizardValues(),
              source: v as typeof SOURCE_NGC | typeof SOURCE_HF | typeof SOURCE_WORKSPACE,
              name: keepName,
            });
          }}
          items={[
            { value: SOURCE_NGC, children: 'NGC NIM Container' },
            { value: SOURCE_HF, children: 'HuggingFace' },
            { value: SOURCE_WORKSPACE, children: 'Workspace' },
          ]}
        />
        {(source === SOURCE_HF || source === SOURCE_WORKSPACE) && (
          <Text kind="body/regular/md">
            Choose the engine that serves this model. vLLM runs any supported architecture from a
            default image; NIM needs an image built for the specific architecture.
          </Text>
        )}

        <ControlledTextInput
          useControllerProps={{ control, name: 'name' }}
          name="name"
          label="Name"
          formFieldProps={{
            slotInfo: 'Name used across all related assets.',
            slotError: errors.name?.message,
          }}
        />

        {source === SOURCE_NGC && <NgcSourceFields control={control} errors={errors} />}
        {source === SOURCE_HF && (
          <HuggingFaceSourceFields
            control={control}
            errors={errors}
            queryEnabled={open && !!workspace}
            workspace={workspace}
          />
        )}
        {source === SOURCE_WORKSPACE && (
          <WorkspaceSourceFields
            control={control}
            errors={errors}
            queryEnabled={open && !!workspace}
            workspace={workspace}
            onPickerTypeChange={(value) => {
              setValue('workspacePickerType', value, {
                shouldDirty: true,
                shouldTouch: true,
                shouldValidate: true,
              });
              if (value === WORKSPACE_PICKER_MODEL) {
                setValue('fileset', '', { shouldDirty: true });
              }
              if (value === WORKSPACE_PICKER_FILESET) {
                setValue('modelRef', '', { shouldDirty: true });
              }
            }}
          />
        )}

        <AdvancedSettingsAccordion
          advancedAccordion={advancedAccordion}
          control={control}
          errors={errors}
          onAdvancedAccordionChange={setAdvancedAccordion}
        />
      </Stack>
    </SidePanel>
  );
};
