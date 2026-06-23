// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledDatasetFileSelect } from '@nemo/common/src/components/DatasetFileSelect/ControlledDatasetFileSelect';
import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { Block, RadioGroup, Stack, Text } from '@nvidia/foundations-react-core';
import { EVAL_CONFIG_FILESET_HELP_TEXT } from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type { EvalConfigChoice } from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { type FC, useEffect } from 'react';
import { useForm, useWatch, type SubmitHandler } from 'react-hook-form';
import { z } from 'zod';

const MODE_DEFAULT = 'default';
const MODE_FILESET = 'fileset';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Use example configuration' },
  { value: MODE_FILESET, children: 'Select or upload a config file from a fileset' },
];

const applyEvalConfigSchema = z
  .object({
    mode: z.enum([MODE_DEFAULT, MODE_FILESET]),
    /** ``ControlledDatasetFileSelect`` stores the selection as
     *  ``workspace/name#path`` (or null when nothing is picked). */
    datasetFile: z.string().nullable(),
  })
  .refine(
    (data) =>
      data.mode !== MODE_FILESET ||
      (typeof data.datasetFile === 'string' &&
        !!parseFilesetLocation(data.datasetFile)?.objectPath),
    {
      message: 'Pick an eval YAML inside an existing fileset',
      path: ['datasetFile'],
    }
  );

type FormShape = z.infer<typeof applyEvalConfigSchema>;

const DEFAULT_VALUES: FormShape = { mode: MODE_DEFAULT, datasetFile: null };

interface ApplyEvalConfigModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  /** Title of the suggestion being applied — surfaced in the modal copy. */
  suggestionTitle: string;
  onConfirm: (choice: EvalConfigChoice) => void;
}

export const ApplyEvalConfigModal: FC<ApplyEvalConfigModalProps> = ({
  open,
  onClose,
  workspace,
  suggestionTitle,
  onConfirm,
}) => {
  const {
    control,
    reset,
    setValue,
    handleSubmit,
    setError,
    clearErrors,
    formState: { errors },
  } = useForm<FormShape>({
    resolver: zodResolver(applyEvalConfigSchema),
    defaultValues: DEFAULT_VALUES,
    mode: 'onSubmit',
    reValidateMode: 'onChange',
  });

  const mode = useWatch({ control, name: 'mode' });

  // Reset the form when the modal closes so the next open starts on the
  // default mode rather than carrying forward the prior choice.
  useEffect(() => {
    if (!open) {
      reset(DEFAULT_VALUES);
    }
  }, [open, reset]);

  const onSubmit: SubmitHandler<FormShape> = (data) => {
    if (data.mode === MODE_FILESET) {
      // Schema refine guarantees ``datasetFile`` parses to a fileset reference
      // with a non-empty ``objectPath`` before reaching this point.
      const parsed = parseFilesetLocation(data.datasetFile!)!;
      onConfirm({
        filesetOverride: { fileset: parsed.name, configPath: parsed.objectPath },
      });
    } else {
      onConfirm({ filesetOverride: null });
    }
  };

  return (
    <FormModal
      open={open}
      onClose={onClose}
      title="Apply optimization"
      submitButtonText="Apply"
      onSubmit={handleSubmit(onSubmit)}
    >
      <Stack gap="density-xl">
        <Block>
          <Text kind="body/regular/sm" color="secondary">
            About to apply: <Text kind="body/semibold/sm">{suggestionTitle}</Text>
          </Text>
        </Block>
        <Block>
          <Text kind="label/bold/sm" color="secondary">
            Evaluation config
          </Text>
          <RadioGroup
            name="eval-config-mode"
            value={mode}
            onValueChange={(v) => {
              setValue('mode', v as typeof MODE_DEFAULT | typeof MODE_FILESET, {
                shouldValidate: false,
              });
              clearErrors('datasetFile');
            }}
            items={EVAL_CONFIG_MODE_ITEMS}
          />
        </Block>
        {mode === MODE_FILESET ? (
          <Stack gap="density-md">
            <Text kind="body/regular/sm" color="secondary">
              {EVAL_CONFIG_FILESET_HELP_TEXT}
            </Text>
            <ControlledDatasetFileSelect
              useControllerProps={{
                control,
                name: 'datasetFile',
                rules: { required: 'Pick an eval YAML inside an existing fileset' },
              }}
              acceptedFileTypes={['.yml', '.yaml']}
              invalidFileMode="disable"
              setError={(error) => setError('datasetFile', error)}
              clearError={() => clearErrors('datasetFile')}
              workspace={workspace}
              inline
              autoCommit
              formFieldProps={{
                slotError: errors.datasetFile?.message,
              }}
            />
          </Stack>
        ) : null}
      </Stack>
    </FormModal>
  );
};
