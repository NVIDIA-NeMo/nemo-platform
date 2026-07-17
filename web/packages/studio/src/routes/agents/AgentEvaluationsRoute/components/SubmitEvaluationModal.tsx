// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledDatasetFileSelect } from '@nemo/common/src/components/DatasetFileSelect/ControlledDatasetFileSelect';
import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { useAgentsListAgents } from '@nemo/sdk/generated/agents/api';
import type { AgentEvaluateJobRequest } from '@nemo/sdk/generated/evaluator/schema';
import { filesDownloadFile } from '@nemo/sdk/generated/platform/api';
import { SegmentedControl, Stack, Text } from '@nvidia/foundations-react-core';
import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import { submitAgentEvalJob } from '@studio/api/evaluation/agent-evaluations';
import {
  ensureEvalConfigFileset,
  type EvalSeedFile,
} from '@studio/api/evaluation/eval-config-fileset';
import { JudgeModelSelect } from '@studio/components/evaluation/JudgeModelSelect';
import {
  EVALUATION_SAMPLE_AGENTS,
  evaluationSampleAgentKeyForAgentName,
  getEvaluationSampleAgent,
} from '@studio/constants/sampleAgents';
import { useJudgeModels } from '@studio/hooks/evaluation/useJudgeModels';
import {
  bareName,
  buildAgentEvalRequestBody,
  generateEvalConfigName,
  MODE_DEFAULT,
  MODE_FILESET,
  parseEvalConfig,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/submitEvaluationSpec';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useRef, useState } from 'react';
import { FormProvider, type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Use Example' },
  { value: MODE_FILESET, children: 'Choose Fileset' },
];

/** Flat filename the reusable config is stored as inside its fileset. */
const EVAL_CONFIG_FILENAME = 'eval-config.json';

const submitEvaluationBaseSchema = z.object({
  agent: z.string().min(1, 'Agent is required'),
  judgeModel: z.string(),
  mode: z.enum([MODE_DEFAULT, MODE_FILESET]),
  exampleKey: z.string(),
  newName: z.string(),
  configFile: z.string().nullable(),
});

type SubmitEvaluationFormData = z.infer<typeof submitEvaluationBaseSchema>;

const makeSubmitEvaluationSchema = (requiresJudgeModel: () => boolean) =>
  submitEvaluationBaseSchema.superRefine((data, ctx) => {
    if (requiresJudgeModel() && !data.judgeModel) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Judge model is required',
        path: ['judgeModel'],
      });
    }
    if (data.mode === MODE_DEFAULT) {
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
    if (data.mode === MODE_FILESET && !parseFilesetLocation(data.configFile ?? '')?.objectPath) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Pick an eval-config.json inside an existing fileset',
        path: ['configFile'],
      });
    }
  });

const makeDefaultValues = (agent?: string): SubmitEvaluationFormData => ({
  agent: agent ?? '',
  judgeModel: '',
  mode: MODE_DEFAULT,
  exampleKey: evaluationSampleAgentKeyForAgentName(agent) ?? EVALUATION_SAMPLE_AGENTS[0]?.key ?? '',
  newName: generateEvalConfigName(),
  configFile: null,
});

interface SubmitEvaluationModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  /** When provided, pre-fills + locks the agent selector. */
  agent?: string;
  /** Called after a successful submission with the new job's name. */
  onSubmitted?: (jobName: string) => void;
}

/** Reads the reusable eval-config.json for this submission: either the selected
 *  example asset (seeded into a new fileset) or an existing fileset's file. */
const loadEvalConfigText = async (
  workspace: string,
  formData: SubmitEvaluationFormData
): Promise<string> => {
  if (formData.mode === MODE_DEFAULT) {
    const example = getEvaluationSampleAgent(formData.exampleKey);
    const content = await fetchSampleText(example.evalConfigPath);
    const files: EvalSeedFile[] = [
      { path: EVAL_CONFIG_FILENAME, content, type: 'application/json' },
    ];
    await ensureEvalConfigFileset(
      workspace,
      formData.newName.trim(),
      new AbortController().signal,
      files,
      'Agent Evaluation Config'
    );
    return content;
  }
  // Choose-fileset mode: read the picked eval-config.json out of its fileset.
  const parsed = parseFilesetLocation(formData.configFile ?? '');
  if (!parsed?.objectPath) throw new Error('No eval-config.json selected');
  const blob = await filesDownloadFile(
    workspace,
    parsed.name,
    parsed.objectPath,
    new AbortController().signal
  );
  if (!blob) throw new Error('Failed to read the selected eval config');
  return blob.text();
};

export const SubmitEvaluationModal: FC<SubmitEvaluationModalProps> = ({
  open,
  onClose,
  workspace,
  agent: agentProp,
  onSubmitted,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  // Ref keeps isLlmJudge current for the zod schema getter at validation time.
  const isLlmJudgeRef = useRef(false);
  const [schema] = useState(() => makeSubmitEvaluationSchema(() => isLlmJudgeRef.current));

  const { data: agentsResponse, isLoading: isAgentsLoading } = useAgentsListAgents(
    workspace,
    undefined,
    { query: { enabled: open && !agentProp } }
  );
  const agents = agentsResponse?.data ?? [];

  const methods = useForm<SubmitEvaluationFormData>({
    resolver: zodResolver(schema),
    defaultValues: makeDefaultValues(agentProp),
    mode: 'onSubmit',
    reValidateMode: 'onChange',
  });
  const {
    control,
    reset: resetForm,
    setValue,
    getValues,
    handleSubmit,
    setError,
    clearErrors,
    formState,
  } = methods;
  const { errors } = formState;

  const mode = useWatch({ control, name: 'mode' });
  const selectedAgent = useWatch({ control, name: 'agent' });
  const exampleKey = useWatch({ control, name: 'exampleKey' });

  // Fetch and parse the selected example config early to detect metric type and default model.
  const { data: exampleConfig } = useQuery({
    queryKey: ['eval-config-preview', exampleKey],
    queryFn: async () => {
      const example = getEvaluationSampleAgent(exampleKey);
      if (!example) return null;
      const text = await fetchSampleText(example.evalConfigPath);
      return parseEvalConfig(text);
    },
    enabled: open && mode === MODE_DEFAULT && !!exampleKey,
    staleTime: Infinity,
  });

  const isLlmJudge = mode === MODE_DEFAULT && exampleConfig?.metric.metric_type === 'llm-judge';
  isLlmJudgeRef.current = isLlmJudge;

  const defaultModelRef =
    isLlmJudge && typeof exampleConfig?.metric.payload.metric.model === 'string'
      ? exampleConfig.metric.payload.metric.model
      : undefined;

  // Fetch judge models eagerly so they're ready when isLlmJudge resolves.
  const { data: judgeModels } = useJudgeModels({ enabled: open });

  // Pre-populate judge model from the config's ModelRef when modal opens or data arrives.
  // Uses getValues (not a reactive watch) to avoid re-running on every model change.
  useEffect(() => {
    if (!open || !isLlmJudge || !defaultModelRef || !judgeModels?.length) return;
    if (getValues('judgeModel')) return;
    const target = bareName(defaultModelRef);
    const match = judgeModels.find((m) => m.name === target);
    if (match) {
      const urn = getURNFromNamedEntityRef(match);
      if (urn) setValue('judgeModel', urn);
    }
  }, [open, isLlmJudge, defaultModelRef, judgeModels, getValues, setValue]);

  const {
    mutateAsync: submitEvaluation,
    error: submitError,
    isPending,
    reset: resetMutation,
  } = useMutation({
    mutationFn: async (formData: SubmitEvaluationFormData) => {
      const configText = await loadEvalConfigText(workspace, formData);
      const config = parseEvalConfig(configText);
      const filesetName =
        formData.mode === MODE_DEFAULT
          ? formData.newName.trim()
          : (parseFilesetLocation(formData.configFile ?? '')?.name ?? undefined);
      const body = buildAgentEvalRequestBody(config, {
        workspace,
        agent: formData.agent,
        judgeModel: formData.judgeModel,
        filesetName,
      });
      const created = await submitAgentEvalJob(workspace, body as AgentEvaluateJobRequest);
      if (!created?.name) throw new Error('Submission did not return a job name');
      return created.name;
    },
    onSuccess: (jobName) => {
      toast.success(`Evaluation "${jobName}" submitted`);
      void queryClient.invalidateQueries({ queryKey: ['agent-eval-jobs', workspace] });
      onSubmitted?.(jobName);
      resetAndClose();
    },
  });

  // Keep the example matched to the agent it was created from.
  useEffect(() => {
    const matchedKey = evaluationSampleAgentKeyForAgentName(selectedAgent);
    if (matchedKey) setValue('exampleKey', matchedKey);
  }, [selectedAgent, setValue]);

  useEffect(() => {
    if (!open) resetForm(makeDefaultValues(agentProp));
  }, [open, agentProp, resetForm]);

  const resetAndClose = () => {
    resetMutation();
    resetForm(makeDefaultValues(agentProp));
    onClose();
  };

  const onSubmit: SubmitHandler<SubmitEvaluationFormData> = async (formData) => {
    try {
      await submitEvaluation(formData);
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
      title="Run Agent Evaluation"
      submitButtonText="Submit"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={errorMessage}
      className="w-[690px]! max-w-[95vw]!"
    >
      <FormProvider {...methods}>
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
              formFieldProps={{ slotLabel: 'Agent', slotError: errors.agent?.message }}
            />
          )}

          {selectedAgent ? (
            <Stack gap="density-xl">
              <Text kind="label/bold/sm" color="secondary">
                Eval Config
              </Text>
              <SegmentedControl
                className="w-full [&_button]:flex-1"
                value={mode}
                onValueChange={(v) => {
                  setValue('mode', v as typeof MODE_DEFAULT | typeof MODE_FILESET, {
                    shouldValidate: false,
                  });
                  clearErrors('configFile');
                }}
                items={EVAL_CONFIG_MODE_ITEMS}
              />

              {mode === MODE_DEFAULT ? (
                <>
                  <ControlledSelect
                    useControllerProps={{ control, name: 'exampleKey' }}
                    items={EVALUATION_SAMPLE_AGENTS.map((example) => ({
                      value: example.key,
                      children: example.label,
                    }))}
                    formFieldProps={{ slotLabel: 'Example', slotError: errors.exampleKey?.message }}
                  />
                  {isLlmJudge && (
                    <JudgeModelSelect<SubmitEvaluationFormData>
                      formFieldName="judgeModel"
                      slotLabel="Judge Model"
                    />
                  )}
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
                    name: 'configFile',
                    rules: { required: 'Pick an eval-config.json inside an existing fileset' },
                  }}
                  acceptedFileTypes={['.json']}
                  invalidFileMode="disable"
                  setError={(error) => setError('configFile', error)}
                  clearError={() => clearErrors('configFile')}
                  workspace={workspace}
                  inline
                  autoCommit
                  autoSelectFirstAcceptable
                  showUpdatedAt
                  filesetPurpose="generic"
                  datasetLabel="Fileset"
                  formFieldProps={{ slotError: errors.configFile?.message }}
                />
              )}
            </Stack>
          ) : null}
        </Stack>
      </FormProvider>
    </FormModal>
  );
};
