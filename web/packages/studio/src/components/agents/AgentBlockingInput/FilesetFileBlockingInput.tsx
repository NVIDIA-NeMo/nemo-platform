// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledDatasetFileSelect } from '@nemo/common/src/components/DatasetFileSelect/ControlledDatasetFileSelect';
import type { AcceptedFileType } from '@nemo/common/src/components/DatasetFileSelect/DatasetFileSelect';
import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { Stack } from '@nvidia/foundations-react-core';
import { AgentBlockingInputFrame } from '@studio/components/agents/AgentBlockingInput/AgentBlockingInputFrame';
import type {
  AgentBlockingInputSecondaryAction,
  FilesetFileBlockingInputProps,
} from '@studio/components/agents/AgentBlockingInput/types';
import { getAcceptedFileTypes } from '@studio/components/agents/AgentBlockingInput/utils';
import { type FC, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const getFilesetFileBlockingInputSchema = (missingSelectionMessage: string) =>
  z.object({
    datasetFile: z
      .string()
      .nullable()
      .refine(
        (value) => {
          if (typeof value !== 'string') return false;
          const parsed = parseFilesetLocation(value);
          return !!parsed?.name.trim() && !!parsed.objectPath.trim();
        },
        { message: missingSelectionMessage }
      ),
  });

type FilesetFileFormData = z.infer<ReturnType<typeof getFilesetFileBlockingInputSchema>>;

interface FilesetFileBlockingInputBaseProps extends FilesetFileBlockingInputProps {
  readonly defaultAcceptedFileTypes: AcceptedFileType[];
  readonly missingSelectionMessage: string;
  readonly onSecondaryAction?: () => Promise<void> | void;
  readonly secondaryActions?: readonly AgentBlockingInputSecondaryAction[];
  readonly secondaryActionLabel?: string;
  readonly selectionDisplayLabel: string;
  readonly submitLabel: string;
  readonly toValue: (parsed: { name: string; objectPath: string }) => Record<string, unknown>;
}

export const FilesetFileBlockingInput: FC<FilesetFileBlockingInputBaseProps> = ({
  defaultAcceptedFileTypes,
  input = {},
  missingSelectionMessage,
  onSecondaryAction,
  onSkip,
  onSubmit,
  request,
  secondaryActions,
  secondaryActionLabel,
  selectionDisplayLabel,
  status = 'pending',
  submitLabel,
  toValue,
  workspace,
}) => {
  const isSubmitting = status === 'submitting';
  const schema = useMemo(
    () => getFilesetFileBlockingInputSchema(missingSelectionMessage),
    [missingSelectionMessage]
  );
  const {
    clearErrors,
    control,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<FilesetFileFormData>({
    defaultValues: { datasetFile: null },
    resolver: zodResolver(schema),
    disabled: isSubmitting,
  });
  const acceptedFileTypes = getAcceptedFileTypes(input, defaultAcceptedFileTypes);
  const datasetFile = watch('datasetFile');

  const submit = handleSubmit((data) => {
    const parsed =
      typeof data.datasetFile === 'string' ? parseFilesetLocation(data.datasetFile) : null;
    if (!parsed?.name.trim() || !parsed.objectPath.trim()) return;

    void onSubmit({
      displayText: `${selectionDisplayLabel}: ${parsed.name}/${parsed.objectPath}`,
      value: toValue({ name: parsed.name, objectPath: parsed.objectPath }),
    });
  });

  return (
    <AgentBlockingInputFrame
      isSubmitting={isSubmitting}
      onSecondaryAction={onSecondaryAction}
      onSkip={onSkip}
      onSubmit={submit}
      request={request}
      secondaryActions={secondaryActions}
      secondaryActionLabel={secondaryActionLabel}
      submitDisabled={!datasetFile}
      submitLabel={submitLabel}
    >
      <Stack className="max-h-[45vh] overflow-y-auto pr-density-sm">
        <ControlledDatasetFileSelect
          useControllerProps={{
            control,
            name: 'datasetFile',
          }}
          acceptedFileTypes={acceptedFileTypes}
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
    </AgentBlockingInputFrame>
  );
};
