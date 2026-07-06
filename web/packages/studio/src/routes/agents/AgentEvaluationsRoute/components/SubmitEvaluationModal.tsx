// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledDatasetFileSelect } from '@nemo/common/src/components/DatasetFileSelect/ControlledDatasetFileSelect';
import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { customFetch } from '@nemo/sdk/generated/fetchers/platform';
import { Block, RadioGroup, Stack, Text } from '@nvidia/foundations-react-core';
import { type Agent } from '@studio/components/dataViews/AgentsDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ensureEvalConfigFileset } from '@studio/routes/agents/AgentSuggestionsRoute/api';
import { SAMPLE_EVAL_CONFIG_PATH } from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import {
  evalFilesetForAgent,
  evalOutputFilesetFor,
} from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect } from 'react';
import { type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

const MODE_DEFAULT = 'default';
const MODE_FILESET = 'fileset';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Use example evaluation config' },
  { value: MODE_FILESET, children: 'Select or upload a config file from a fileset' },
];

const submitEvaluationSchema = z
  .object({
    agent: z.string().min(1, 'Agent is required'),
    mode: z.enum([MODE_DEFAULT, MODE_FILESET]),
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

type SubmitEvaluationFormData = z.infer<typeof submitEvaluationSchema>;

const SUFFIX_LENGTH = 5;
const SUFFIX_ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789';

/** Mirrors the optimizer's randomSiblingSuffix so this surface looks the
 *  same; isolated copy so the form doesn't reach into utils.ts internals. */
const randomSuffix = (): string => {
  const bytes = new Uint8Array(SUFFIX_LENGTH);
  crypto.getRandomValues(bytes);
  let out = '';
  for (const b of bytes) out += SUFFIX_ALPHABET[b % SUFFIX_ALPHABET.length];
  return out;
};

const makeDefaultValues = (agent?: string): SubmitEvaluationFormData => ({
  agent: agent ?? '',
  mode: MODE_DEFAULT,
  datasetFile: null,
});

interface SubmitEvaluationModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  /** Workspace to submit the eval into. Passed in (rather than resolved
   *  from the URL) so the modal can render outside a workspace route — e.g.
   *  inside an open ``AgentPanel`` test. */
  workspace: string;
  /** When provided, pre-fills + locks the agent selector. */
  agent?: string;
  /** Called after a successful submission with the new job's name. */
  onSubmitted?: (jobName: string) => void;
}

interface SubmitSpec {
  agent: string;
  evalConfig: string;
  evalConfigFileset: string;
  /** When true, seed the bundled sample into ``evalConfigFileset`` before
   *  POSTing to ``/jobs/evaluate``. Skipped when the user picks an existing
   *  fileset since we shouldn't overwrite their files. */
  seedSample: boolean;
}

export const SubmitEvaluationModal: FC<SubmitEvaluationModalProps> = ({
  open,
  onClose,
  workspace,
  agent: agentProp,
  onSubmitted,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  const { data: agents = [], isLoading: isAgentsLoading } = useQuery({
    queryKey: ['agents', workspace],
    queryFn: async () => {
      const response = await fetch(
        `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${workspace}/agents`
      );
      if (!response.ok) throw new Error('Failed to fetch agents');
      const json = (await response.json()) as { data: Agent[] };
      return json.data;
    },
    enabled: open && !agentProp,
  });

  const {
    mutateAsync: submitEvaluation,
    error: submitError,
    isPending,
    reset: resetMutation,
  } = useMutation({
    mutationFn: async (spec: SubmitSpec) => {
      if (spec.seedSample) {
        // Default mode: seed the per-agent eval-config fileset with the
        // bundled sample so the user doesn't have to pre-upload anything.
        await ensureEvalConfigFileset(
          workspace,
          spec.evalConfigFileset,
          new AbortController().signal
        );
      }
      const body = {
        spec: {
          agent: spec.agent,
          eval_config: spec.evalConfig,
          eval_config_fileset: spec.evalConfigFileset,
          // Auto-generated per submission so re-running for the same agent
          // doesn't 409 on an existing output fileset.
          output: `${evalOutputFilesetFor(spec.agent)}-${randomSuffix()}`,
        },
      };
      const res = await customFetch<{ name?: string }>({
        url: `/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/jobs/evaluate`,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        data: body,
      });
      if (!res?.name) {
        throw new Error('Submission did not return a job name');
      }
      return res.name;
    },
    onSuccess: (jobName) => {
      toast.success(`Evaluation "${jobName}" submitted`);
      void queryClient.invalidateQueries({ queryKey: ['agent-eval-jobs', workspace] });
      onSubmitted?.(jobName);
      resetAndClose();
    },
  });

  const {
    control,
    reset: resetForm,
    setValue,
    handleSubmit,
    setError,
    clearErrors,
    formState: { errors },
  } = useForm<SubmitEvaluationFormData>({
    resolver: zodResolver(submitEvaluationSchema),
    defaultValues: makeDefaultValues(agentProp),
    disabled: isPending,
    mode: 'onSubmit',
    reValidateMode: 'onChange',
  });

  const mode = useWatch({ control, name: 'mode' });

  useEffect(() => {
    resetForm(makeDefaultValues(agentProp));
  }, [agentProp, resetForm]);

  useEffect(() => {
    if (!open) {
      resetForm(makeDefaultValues(agentProp));
    }
  }, [open, agentProp, resetForm]);

  const reset = () => {
    resetMutation();
    resetForm(makeDefaultValues(agentProp));
  };

  const resetAndClose = () => {
    reset();
    onClose();
  };

  const onSubmit: SubmitHandler<SubmitEvaluationFormData> = async (formData) => {
    let spec: SubmitSpec;
    if (formData.mode === MODE_FILESET) {
      // Schema refine guarantees ``datasetFile`` parses to a fileset reference
      // with a non-empty ``objectPath`` before reaching this point.
      const parsed = parseFilesetLocation(formData.datasetFile!)!;
      spec = {
        agent: formData.agent,
        evalConfig: parsed.objectPath,
        evalConfigFileset: parsed.name,
        seedSample: false,
      };
    } else {
      spec = {
        agent: formData.agent,
        evalConfig: SAMPLE_EVAL_CONFIG_PATH,
        evalConfigFileset: evalFilesetForAgent(formData.agent),
        seedSample: true,
      };
    }
    try {
      await submitEvaluation(spec);
    } catch {
      // Error rendered via errorText prop.
    }
  };

  const errorMessage =
    submitError instanceof Error
      ? submitError.message
      : submitError
        ? 'An error occurred'
        : undefined;

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      title="Run Evaluation"
      submitButtonText="Submit"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={errorMessage}
    >
      <Stack gap="density-xl">
        {agentProp ? (
          <Text kind="body/regular/sm" color="secondary">
            Evaluating agent <Text kind="body/semibold/sm">{agentProp}</Text>
          </Text>
        ) : (
          <ControlledSelect
            useControllerProps={{ control, name: 'agent' }}
            loading={isAgentsLoading}
            items={agents.flatMap((agent) =>
              agent.name ? [{ value: agent.name, children: agent.name }] : []
            )}
            formFieldProps={{
              slotLabel: 'Agent',
              slotError: errors.agent?.message,
            }}
          />
        )}
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
            filesetPurposeFilter={null}
            filesetLabel="Filesets"
            inline
            autoCommit
            formFieldProps={{
              slotError: errors.datasetFile?.message,
            }}
          />
        ) : null}
      </Stack>
    </FormModal>
  );
};
