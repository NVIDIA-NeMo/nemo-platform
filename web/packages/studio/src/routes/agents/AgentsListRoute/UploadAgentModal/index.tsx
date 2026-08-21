// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { getErrorMessage } from '@nemo/common/src/api/common/utils';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey } from '@nemo/sdk/generated/agents/api';
import {
  Stack,
  Text,
  UploadInputElement,
  UploadRoot,
  UploadTrigger,
} from '@nvidia/foundations-react-core';
import {
  AgentSpecFilesetOrphanError,
  useCreateAgentFromUpload,
} from '@studio/api/agents/useCreateAgentFromUpload';
import {
  AGENT_CONFIG_FILENAME,
  uploadAgentFormSchema,
} from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/const';
import type {
  UploadAgentEntry,
  UploadAgentFormData,
  UploadAgentModalProps,
} from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/type';
import {
  agentNameFromConfig,
  collectAgentEntries,
  findNonUtf8Path,
  parseAgentConfig,
  tooManyPickedFiles,
  totalEntryBytes,
  validateAgentEntries,
} from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/utils';
import { getAgentDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type ChangeEventHandler, type FC, useCallback, useMemo, useRef, useState } from 'react';
import { type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';

export const UploadAgentModal: FC<UploadAgentModalProps> = ({ open, onClose, workspace }) => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const inputRef = useRef<HTMLInputElement>(null);
  const setDirectoryInput = useCallback((node: HTMLInputElement | null) => {
    inputRef.current = node;
    // webkitdirectory is absent from React's input attribute types.
    node?.setAttribute('webkitdirectory', '');
  }, []);
  const [entries, setEntries] = useState<UploadAgentEntry[]>([]);
  const [directoryName, setDirectoryName] = useState('');
  const [selectionError, setSelectionError] = useState<string | undefined>(undefined);
  const [replaceArmedFor, setReplaceArmedFor] = useState<string | null>(null);

  const {
    mutateAsync: createAgent,
    error: createError,
    isPending,
    reset: resetMutation,
  } = useCreateAgentFromUpload({
    onSuccess: (agent) => {
      toast.success(`Agent "${agent.name}" created`);
      void queryClient.invalidateQueries({ queryKey: getAgentsListAgentsQueryKey(workspace) });
      resetAndClose();
      if (agent.name) navigate(getAgentDetailRoute(workspace, agent.name));
    },
  });

  const {
    control,
    setValue,
    handleSubmit,
    reset: resetForm,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(uploadAgentFormSchema),
    defaultValues: { name: '' },
    disabled: isPending,
    mode: 'onChange',
  });

  // useWatch re-renders this modal on every keystroke; the summary depends only on entries.
  const entriesSummary = useMemo(
    () =>
      entries.length === 0
        ? undefined
        : `${directoryName} — ${entries.length} files, ${Math.max(1, Math.round(totalEntryBytes(entries) / 1000))} KB`,
    [directoryName, entries]
  );

  const watchedName = useWatch({ control, name: 'name' });
  // Derived, not stored: an armed replace targets one fileset, so editing the name
  // disarms it in the same render rather than one render later.
  const replaceOrphan = replaceArmedFor !== null && replaceArmedFor === watchedName?.trim();

  const resetAndClose = () => {
    resetMutation();
    resetForm({ name: '' });
    setEntries([]);
    setDirectoryName('');
    setSelectionError(undefined);
    setReplaceArmedFor(null);
    onClose();
  };

  const onDirectoryPicked: ChangeEventHandler<HTMLInputElement> = async (event) => {
    // Read the count off the FileList before materialising it: an accidental pick can
    // carry hundreds of thousands of files, and Array.from on that is itself the stall.
    const fileList = event.target.files;
    const pickedCount = fileList?.length ?? 0;
    if (pickedCount === 0) return;

    const oversized = tooManyPickedFiles(pickedCount);
    if (oversized) {
      event.target.value = '';
      setEntries([]);
      setDirectoryName('');
      setSelectionError(oversized);
      return;
    }

    const picked = Array.from(fileList ?? []);
    event.target.value = '';
    setDirectoryName(picked[0]?.webkitRelativePath.split('/')[0] ?? '');

    const collected = collectAgentEntries(picked);

    const problem = validateAgentEntries(collected);
    if (problem) {
      setEntries([]);
      setSelectionError(problem);
      return;
    }

    const binaryPath = await findNonUtf8Path(collected);
    if (binaryPath) {
      setEntries([]);
      setSelectionError(
        `${binaryPath} is not a text file. Agent files are delivered to container deployments as text, so the agent would fail to deploy. Remove it and try again.`
      );
      return;
    }

    const configEntry = collected.find((item) => item.path === AGENT_CONFIG_FILENAME);
    try {
      const config = parseAgentConfig((await configEntry?.file.text()) ?? '');
      setValue('name', agentNameFromConfig(config) ?? '', { shouldValidate: true });
    } catch (error) {
      setEntries([]);
      setSelectionError(
        getErrorMessage(error as Error) || `Could not read ${AGENT_CONFIG_FILENAME}`
      );
      return;
    }

    setEntries(collected);
    setSelectionError(undefined);
  };

  const onSubmit: SubmitHandler<UploadAgentFormData> = async (formData) => {
    const name = formData.name.trim();
    try {
      await createAgent({ workspace, name, entries, replaceOrphanedFileset: replaceOrphan });
    } catch (error) {
      // An orphaned fileset is recoverable, so the next submit replaces it.
      setReplaceArmedFor(error instanceof AgentSpecFilesetOrphanError ? name : null);
    }
  };

  // No fallback argument: getErrorMessage prefers one over a plain Error's own message.
  const errorMessage =
    selectionError ??
    (createError ? getErrorMessage(createError as Error) || 'Failed to create agent' : undefined);

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      className="w-[720px] max-w-[90vw]"
      title="Upload agent configuration"
      instruction="Integrated agents allow users to evaluate, optimize, and deploy agents."
      submitButtonText={replaceOrphan ? 'Replace and create' : 'Create'}
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      submitDisabled={entries.length === 0}
      errorText={errorMessage}
    >
      <Stack gap="density-md">
        <Text kind="label/semibold/md">Select agent config files</Text>
        <UploadRoot multiple disabled={isPending}>
          <UploadTrigger
            className="w-full"
            slotAnchor={directoryName ? 'Choose a different directory' : 'Choose a directory'}
            slotHeaderText=" containing agent.yaml."
          >
            <UploadInputElement
              ref={setDirectoryInput}
              data-testid="agent-directory-input"
              multiple
              onChange={onDirectoryPicked}
            />
          </UploadTrigger>
        </UploadRoot>
        {entriesSummary ? <Text kind="body/regular/sm">{entriesSummary}</Text> : null}
        <ControlledTextInput
          useControllerProps={{ control, name: 'name' }}
          label="Name"
          formFieldProps={{ slotError: errors.name?.message }}
        />
      </Stack>
    </FormModal>
  );
};
