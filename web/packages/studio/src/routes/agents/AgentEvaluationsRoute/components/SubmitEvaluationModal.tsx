// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledDatasetFileSelect } from '@nemo/common/src/components/DatasetFileSelect/ControlledDatasetFileSelect';
import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { customFetch } from '@nemo/sdk/generated/fetchers/platform';
import { filesCreateFileset } from '@nemo/sdk/generated/platform/api';
import { SegmentedControl, Stack, Text } from '@nvidia/foundations-react-core';
import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import { type Agent } from '@studio/components/dataViews/AgentsDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import {
  DEFAULT_SAMPLE_AGENT_KEY,
  SAMPLE_AGENTS,
  sampleAgentKeyForAgentName,
} from '@studio/constants/sampleAgents';
import {
  fetchAgentEvalJobs,
  type AgentEvalJob,
} from '@studio/routes/agents/AgentEvaluationsRoute/api';
import {
  buildSubmitSpec,
  CREATE_NEW,
  evalOutputDescription,
  evaluateRequestBody,
  generateEvalConfigName,
  generateOutputFilesetName,
  MODE_DEFAULT,
  MODE_FILESET,
  type SubmitSpec,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/submitEvaluationSpec';
import {
  ensureEvalConfigFileset,
  type EvalSeedFile,
} from '@studio/routes/agents/AgentSuggestionsRoute/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useMemo, useRef } from 'react';
import { type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Use Example' },
  { value: MODE_FILESET, children: 'Choose Fileset' },
];

/** Strip an optional ``workspace/`` prefix so agent references compare by name. */
const bareName = (value?: string | null): string | null => {
  if (typeof value !== 'string' || value.length === 0) return null;
  return value.includes('/') ? (value.split('/').pop() ?? null) : value;
};

const submitEvaluationSchema = z
  .object({
    agent: z.string().min(1, 'Agent is required'),
    // Existing eval-config fileset to reuse, or CREATE_NEW to make one.
    evalConfig: z.string().min(1, 'Select or create an eval config'),
    // Create-mode fields (only enforced when evalConfig === CREATE_NEW).
    newName: z.string(),
    mode: z.enum([MODE_DEFAULT, MODE_FILESET]),
    exampleKey: z.string(),
    datasetFile: z.string().nullable(),
  })
  .superRefine((data, ctx) => {
    if (data.evalConfig !== CREATE_NEW) return;
    if (data.mode === MODE_DEFAULT) {
      // newName becomes the fileset name — enforce the platform naming rules.
      const name = data.newName.trim();
      if (!name) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Name is required',
          path: ['newName'],
        });
      } else if (!/^[a-zA-Z0-9_.-]+$/.test(name)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Use only letters, digits, dots, hyphens, and underscores',
          path: ['newName'],
        });
      }
    }
    if (data.mode === MODE_FILESET && !parseFilesetLocation(data.datasetFile ?? '')?.objectPath) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Pick an eval YAML inside an existing fileset',
        path: ['datasetFile'],
      });
    }
  });

type SubmitEvaluationFormData = z.infer<typeof submitEvaluationSchema>;

const makeDefaultValues = (agent?: string): SubmitEvaluationFormData => ({
  agent: agent ?? '',
  // Default to create; existing configs are one click away in the dropdown.
  evalConfig: CREATE_NEW,
  newName: generateEvalConfigName(),
  mode: MODE_DEFAULT,
  // Auto-match the example to the agent it was created from (by name prefix),
  // falling back to the first example for non-example agents.
  exampleKey: sampleAgentKeyForAgentName(agent) ?? DEFAULT_SAMPLE_AGENT_KEY,
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

  // Prior eval jobs — the source for the "existing eval config" dropdown.
  const { data: jobs = [], isLoading: isJobsLoading } = useQuery({
    queryKey: ['agent-eval-jobs', workspace],
    queryFn: ({ signal }) => fetchAgentEvalJobs(workspace, signal),
    enabled: open,
  });

  const {
    mutateAsync: submitEvaluation,
    error: submitError,
    isPending,
    reset: resetMutation,
  } = useMutation({
    mutationFn: async (spec: SubmitSpec) => {
      if (spec.seedSources) {
        // Seed the selected example's eval assets into the new config fileset.
        const files: EvalSeedFile[] = await Promise.all(
          spec.seedSources.map(async (source) => ({
            path: source.path,
            content: await fetchSampleText(source.assetPath),
            type: source.type,
          }))
        );
        await ensureEvalConfigFileset(
          workspace,
          spec.evalConfigFileset,
          new AbortController().signal,
          files,
          'Agent Evaluation Config'
        );
      }
      // Pre-create the output fileset so it carries a description; the job's
      // auto-create no-ops once it exists. Best-effort — never block submission.
      const outputFileset = generateOutputFilesetName(spec.agent);
      try {
        await filesCreateFileset(workspace, {
          name: outputFileset,
          description: evalOutputDescription(spec),
          purpose: 'generic',
        });
      } catch {
        // Job still auto-creates the fileset (without a description).
      }
      const body = evaluateRequestBody(spec, outputFileset);
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

  const evalConfig = useWatch({ control, name: 'evalConfig' });
  const mode = useWatch({ control, name: 'mode' });
  const selectedAgent = useWatch({ control, name: 'agent' });

  // Existing eval configs for the agent: distinct config filesets from prior
  // jobs, mapped to the YAML each ran.
  const existingConfigs = useMemo(() => {
    const map = new Map<string, string>();
    const agentKey = bareName(selectedAgent);
    if (!agentKey) return map;
    for (const job of jobs as AgentEvalJob[]) {
      if (bareName(job.spec.agent) !== agentKey) continue;
      const fileset = job.spec.eval_config_fileset;
      if (typeof fileset === 'string' && fileset.length > 0 && !map.has(fileset)) {
        map.set(fileset, job.spec.eval_config ?? '');
      }
    }
    return map;
  }, [jobs, selectedAgent]);

  const evalConfigItems = useMemo(
    () => [
      ...Array.from(existingConfigs.keys()).map((fileset) => ({
        value: fileset,
        children: fileset,
      })),
      { value: CREATE_NEW, children: '+ Create new eval config' },
    ],
    [existingConfigs]
  );

  // When the chosen agent maps to a known example, auto-select its eval config.
  useEffect(() => {
    const matchedKey = sampleAgentKeyForAgentName(selectedAgent);
    if (matchedKey) setValue('exampleKey', matchedKey);
  }, [selectedAgent, setValue]);

  // Preselect the latest existing config for the agent (else create). Ref-guarded
  // to run once per agent so it doesn't override the user's later manual pick.
  const autoSelectedAgentRef = useRef<string | null>(null);
  useEffect(() => {
    if (!open) {
      autoSelectedAgentRef.current = null;
      return;
    }
    if (isJobsLoading || !selectedAgent) return;
    if (autoSelectedAgentRef.current === selectedAgent) return;
    autoSelectedAgentRef.current = selectedAgent;
    const latest = existingConfigs.keys().next().value;
    setValue('evalConfig', latest ?? CREATE_NEW);
  }, [open, isJobsLoading, selectedAgent, existingConfigs, setValue]);

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
    try {
      await submitEvaluation(buildSubmitSpec(formData, existingConfigs));
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

  const isCreating = evalConfig === CREATE_NEW;

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      title="Run Agent Evaluation"
      submitButtonText="Submit"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={errorMessage}
      className="w-[690px]! max-w-[95vw]!"
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
        {selectedAgent ? (
          <Stack gap="density-xl">
            <Text kind="label/bold/sm" color="secondary">
              Eval Config
            </Text>
            <ControlledSelect
              useControllerProps={{ control, name: 'evalConfig' }}
              loading={isJobsLoading}
              items={evalConfigItems}
              formFieldProps={{
                slotError: errors.evalConfig?.message,
              }}
            />
            {isCreating && (
              <>
                <SegmentedControl
                  className="w-full [&_button]:flex-1"
                  value={mode}
                  onValueChange={(v) => {
                    setValue('mode', v as typeof MODE_DEFAULT | typeof MODE_FILESET, {
                      shouldValidate: false,
                    });
                    clearErrors('datasetFile');
                  }}
                  items={EVAL_CONFIG_MODE_ITEMS}
                />
                {mode === MODE_DEFAULT ? (
                  <>
                    <ControlledSelect
                      useControllerProps={{ control, name: 'exampleKey' }}
                      items={SAMPLE_AGENTS.map((example) => ({
                        value: example.key,
                        children: example.label,
                      }))}
                      formFieldProps={{
                        slotLabel: 'Example',
                        slotError: errors.exampleKey?.message,
                      }}
                    />
                    <ControlledTextInput
                      useControllerProps={{ control, name: 'newName' }}
                      selectOnFocus
                      formFieldProps={{
                        slotLabel: 'New Fileset Name',
                        slotError: errors.newName?.message,
                      }}
                    />
                  </>
                ) : (
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
                    autoSelectFirstAcceptable
                    filesetPurpose="generic"
                    datasetLabel="Fileset"
                    formFieldProps={{
                      slotError: errors.datasetFile?.message,
                    }}
                  />
                )}
              </>
            )}
          </Stack>
        ) : null}
      </Stack>
    </FormModal>
  );
};
