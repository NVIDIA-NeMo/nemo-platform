// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { getErrorMessage } from '@nemo/common/src/api/common/utils';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey } from '@nemo/sdk/generated/agents/api';
import { Button, Stack, Text } from '@nvidia/foundations-react-core';
import {
  AgentSpecFilesetOrphanError,
  useCreateAgentFromUpload,
} from '@studio/api/agents/useCreateAgentFromUpload';
import {
  AGENT_CONFIG_FILENAME,
  agentNameFromConfig,
  collectAgentEntries,
  findNonUtf8Path,
  parseAgentConfig,
  totalEntryBytes,
  uploadAgentFormSchema,
  validateAgentEntries,
} from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/const';
import type {
  UploadAgentEntry,
  UploadAgentFormData,
  UploadAgentModalProps,
} from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/type';
import { getAgentDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type ChangeEventHandler, type FC, useEffect, useRef, useState } from 'react';
import { type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';

export const UploadAgentModal: FC<UploadAgentModalProps> = ({ open, onClose, workspace }) => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const inputRef = useRef<HTMLInputElement>(null);
  const [entries, setEntries] = useState<UploadAgentEntry[]>([]);
  const [directoryName, setDirectoryName] = useState('');
  const [selectionError, setSelectionError] = useState<string | undefined>(undefined);
  const [replaceOrphan, setReplaceOrphan] = useState(false);

  // webkitdirectory is absent from React's input attribute types.
  useEffect(() => {
    inputRef.current?.setAttribute('webkitdirectory', '');
  }, [open]);

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

  const watchedName = useWatch({ control, name: 'name' });

  // The armed replace targets one fileset; a different name must re-confirm.
  useEffect(() => {
    setReplaceOrphan(false);
  }, [watchedName]);

  const resetAndClose = () => {
    resetMutation();
    resetForm({ name: '' });
    setEntries([]);
    setDirectoryName('');
    setSelectionError(undefined);
    setReplaceOrphan(false);
    onClose();
  };

  const onDirectoryPicked: ChangeEventHandler<HTMLInputElement> = async (event) => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (picked.length === 0) return;

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
    try {
      await createAgent({
        workspace,
        name: formData.name.trim(),
        entries,
        replaceOrphanedFileset: replaceOrphan,
      });
    } catch (error) {
      // An orphaned fileset is recoverable, so the next submit replaces it.
      setReplaceOrphan(error instanceof AgentSpecFilesetOrphanError);
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
      title="Upload Agent"
      instruction={`Select a directory containing ${AGENT_CONFIG_FILENAME}. Its skills, MCP servers, and prompts are uploaded with it.`}
      submitButtonText={replaceOrphan ? 'Replace and create' : 'Create'}
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      submitDisabled={entries.length === 0}
      errorText={errorMessage}
    >
      <Stack gap="density-md">
        <input ref={inputRef} type="file" multiple hidden onChange={onDirectoryPicked} />
        <Button kind="secondary" onClick={() => inputRef.current?.click()} disabled={isPending}>
          {directoryName ? 'Choose a different directory' : 'Choose directory'}
        </Button>
        {entries.length > 0 ? (
          <Text kind="body/regular/sm">
            {`${directoryName} — ${entries.length} files, ${Math.max(1, Math.round(totalEntryBytes(entries) / 1000))} KB`}
          </Text>
        ) : null}
      </Stack>
      <ControlledTextInput
        useControllerProps={{ control, name: 'name' }}
        label="Name"
        formFieldProps={{ slotError: errors.name?.message }}
      />
    </FormModal>
  );
};
