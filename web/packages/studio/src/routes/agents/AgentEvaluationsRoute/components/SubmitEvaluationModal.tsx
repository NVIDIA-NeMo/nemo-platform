// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { CardSelect } from '@nemo/common/src/components/CardSelect';
import { ControlledDatasetFileSelect } from '@nemo/common/src/components/DatasetFileSelect/ControlledDatasetFileSelect';
import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getEntityNameError } from '@nemo/common/src/utils/entityName';
import { useAgentsListAgents, useAgentsListDeployments } from '@nemo/sdk/generated/agents/api';
import type { AgentsListDeploymentsParams } from '@nemo/sdk/generated/agents/schema/AgentsListDeploymentsParams';
import { evaluatorCreateEvaluateJob } from '@nemo/sdk/generated/evaluator/api';
import type {
  AgentEvaluateJobRequest,
  EvaluateJobRequest,
} from '@nemo/sdk/generated/evaluator/schema';
import {
  filesCreateFileset,
  filesDeleteFileset,
  filesDownloadFile,
  filesUploadFile,
} from '@nemo/sdk/generated/platform/api';
import { Anchor, SegmentedControl, Stack, Text } from '@nvidia/foundations-react-core';
import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import { submitAgentEvalJob } from '@studio/api/evaluation/agent-evaluations';
import { isConflictError, type EvalSeedFile } from '@studio/api/evaluation/eval-config-fileset';
import { JudgeModelSelect } from '@studio/components/evaluation/JudgeModelSelect';
import { LINK_EVAL_DOCS_APPROACHES } from '@studio/constants/links';
import {
  DEFAULT_EVAL_CONFIG_KEY,
  EVAL_CONFIG_SAMPLES,
  getEvalConfigSample,
} from '@studio/constants/sampleAgents';
import { useJudgeModels } from '@studio/hooks/evaluation/useJudgeModels';
import {
  bareName,
  buildAgentEvalRequestBody,
  buildDatasetEvalRequestBody,
  buildPersistedSpec,
  type EvalSpec,
  injectJudgeModel,
  type InlineMetricBundle,
  isDatasetEvalSpec,
  generateEvalConfigName,
  MODE_DEFAULT,
  MODE_FILESET,
  parseEvalConfig,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/submitEvaluationSpec';
import {
  getAgentEvaluationDetailRoute,
  getEvaluationResultDetailsRoute,
} from '@studio/routes/utils';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useRef, useState } from 'react';
import { FormProvider, type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Use Example' },
  { value: MODE_FILESET, children: 'Choose Fileset' },
];

/** Flat filename the reusable config is stored as inside its fileset. */
const EVAL_CONFIG_FILENAME = 'eval-config.json';
const DATASET_FILENAME = 'dataset.jsonl';
const README_FILENAME = 'README.md';

const NO_DEPLOYMENT_MESSAGE = 'This agent has no active deployment.';

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
      const nameError = getEntityNameError(data.newName.trim());
      if (nameError) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: nameError,
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

/** Narrows the deployments list to one agent's running deployments, so the modal never
 *  pages through a workspace-wide list to answer a per-agent question. The endpoint
 *  accepts these as deepObject query params (``filter[agent]``, ``filter[status]``) and
 *  the fetcher serializes nested objects that way, but the generated params type omits
 *  ``filter`` — the agents plugin never declares it via ``openapi_extra`` — hence the cast. */
const runningDeploymentsQuery = (agent: string): AgentsListDeploymentsParams =>
  ({ filter: { agent: bareName(agent), status: 'running' } }) as AgentsListDeploymentsParams;

const makeDefaultValues = (agent?: string): SubmitEvaluationFormData => ({
  agent: agent ?? '',
  judgeModel: '',
  mode: MODE_DEFAULT,
  exampleKey: DEFAULT_EVAL_CONFIG_KEY,
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

/** Resolves the persisted yardstick spec for this submission. In "Use Example" mode
 *  it builds the spec from the sample template (fanning the metric onto every task with
 *  the picked judge baked in) and seeds it into a new fileset; in "Choose Fileset" mode
 *  it reads the saved spec back verbatim (no re-fan, no judge re-pick). */
const loadPersistedSpec = async (
  workspace: string,
  formData: SubmitEvaluationFormData
): Promise<EvalSpec> => {
  if (formData.mode === MODE_DEFAULT) {
    const signal = new AbortController().signal;
    const name = formData.newName.trim();
    const example = getEvalConfigSample(formData.exampleKey);
    const template = parseEvalConfig(await fetchSampleText(example.configPath));
    const files: EvalSeedFile[] = [];
    let spec: EvalSpec;

    if (isDatasetEvalSpec(template)) {
      const judgeModel = formData.judgeModel || null;
      const bakedMetrics = judgeModel
        ? template.metrics.map((m) => injectJudgeModel(m, judgeModel))
        : template.metrics;
      if (example.datasetPath) {
        const datasetFile = example.datasetPath.split('/').pop() ?? DATASET_FILENAME;
        files.push({
          path: datasetFile,
          content: await fetchSampleText(example.datasetPath),
          type: 'application/jsonl',
        });
        spec = {
          ...template,
          dataset: `${workspace}/${name}#${datasetFile}`,
          metrics: bakedMetrics,
        };
      } else {
        spec = { ...template, dataset: [], metrics: bakedMetrics };
      }
    } else {
      spec = buildPersistedSpec(template, formData.judgeModel || null);
    }

    files.push({
      path: EVAL_CONFIG_FILENAME,
      content: JSON.stringify(spec, null, 2),
      type: 'application/json',
    });

    if (example.readmePath) {
      const readme = await fetchSampleText(example.readmePath).catch(() => null);
      if (readme) {
        files.push({ path: README_FILENAME, content: readme, type: 'text/markdown' });
      }
    }

    try {
      await filesCreateFileset(workspace, { name, description: 'Agent Evaluation Config' }, signal);
    } catch (err) {
      if (isConflictError(err)) {
        throw new Error(`A fileset named "${name}" already exists — choose a different name`);
      }
      throw err;
    }
    try {
      for (const f of files) {
        await filesUploadFile(
          workspace,
          name,
          f.path,
          new Blob([f.content], { type: f.type }),
          signal
        );
      }
    } catch (uploadErr) {
      await filesDeleteFileset(workspace, name, signal).catch(() => {});
      throw uploadErr;
    }
    return spec;
  }
  // Choose-fileset mode: read the saved yardstick spec out of its fileset, as-is.
  const parsed = parseFilesetLocation(formData.configFile ?? '');
  if (!parsed?.objectPath) throw new Error('No eval-config.json selected');
  const blob = await filesDownloadFile(
    workspace,
    parsed.name,
    parsed.objectPath,
    new AbortController().signal
  );
  if (!blob) throw new Error('Failed to read the selected eval config');
  return parseEvalConfig(await blob.text());
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
  const navigate = useNavigate();

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

  const { data: runningDeployments, isLoading: isDeploymentsLoading } = useAgentsListDeployments(
    workspace,
    runningDeploymentsQuery(selectedAgent),
    { query: { enabled: open && Boolean(selectedAgent) } }
  );

  const hasRunningDeployment = (runningDeployments?.data ?? []).length > 0;

  const noDeploymentError =
    selectedAgent && !isDeploymentsLoading && !hasRunningDeployment
      ? NO_DEPLOYMENT_MESSAGE
      : undefined;

  const agentFieldError = errors.agent?.message ?? noDeploymentError;
  const exampleKey = useWatch({ control, name: 'exampleKey' });

  // Fetch and parse the selected example config early to detect metric type and default model.
  const { data: exampleConfig } = useQuery({
    queryKey: ['eval-config-preview', exampleKey],
    queryFn: async () => {
      const example = getEvalConfigSample(exampleKey);
      if (!example) return null;
      const text = await fetchSampleText(example.configPath);
      return parseEvalConfig(text);
    },
    enabled: open && mode === MODE_DEFAULT && !!exampleKey,
    staleTime: Infinity,
    // Retain the prior example's parsed config while the next one loads so the
    // judge picker stays mounted (all examples are llm-judge) — no flicker.
    placeholderData: keepPreviousData,
  });

  const configMetrics: InlineMetricBundle[] = !exampleConfig
    ? []
    : isDatasetEvalSpec(exampleConfig)
      ? exampleConfig.metrics
      : exampleConfig.tasks.flatMap((task) => task.metrics);

  const judgeMetric = configMetrics.find((metric) => metric.metric_type === 'llm-judge');

  const isLlmJudge = mode === MODE_DEFAULT && !!judgeMetric;
  isLlmJudgeRef.current = isLlmJudge;

  const defaultModelRef =
    isLlmJudge && typeof judgeMetric?.payload.metric.model === 'string'
      ? judgeMetric.payload.metric.model
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
      const spec = await loadPersistedSpec(workspace, formData);
      const filesetName =
        formData.mode === MODE_DEFAULT
          ? formData.newName.trim()
          : (parseFilesetLocation(formData.configFile ?? '')?.name ?? undefined);
      const selections = { workspace, agent: formData.agent, filesetName };
      const created = isDatasetEvalSpec(spec)
        ? await evaluatorCreateEvaluateJob(
            workspace,
            buildDatasetEvalRequestBody(spec, selections, null) as EvaluateJobRequest
          )
        : await submitAgentEvalJob(
            workspace,
            buildAgentEvalRequestBody(spec, selections) as AgentEvaluateJobRequest
          );
      if (!created?.name) throw new Error('Submission did not return a job name');
      return { name: created.name, isDataset: isDatasetEvalSpec(spec) };
    },
    onSuccess: ({ name, isDataset }) => {
      toast.success(`Evaluation "${name}" submitted`);
      void queryClient.invalidateQueries({ queryKey: ['agent-eval-jobs', workspace] });
      onSubmitted?.(name);
      resetAndClose();
      navigate(
        isDataset
          ? getEvaluationResultDetailsRoute(workspace, name)
          : getAgentEvaluationDetailRoute(workspace, name)
      );
    },
  });

  useEffect(() => {
    if (!open) resetForm(makeDefaultValues(agentProp));
  }, [open, agentProp, resetForm]);

  // Seed the locked agent on open. A blanket reset here would clobber the judge-model
  // preselect above, which runs earlier in effect order.
  useEffect(() => {
    if (open && agentProp) setValue('agent', agentProp);
  }, [open, agentProp, setValue]);

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
      submitDisabled={Boolean(noDeploymentError)}
      loading={isPending}
      errorText={errorMessage}
      className="w-[690px]! max-w-[95vw]!"
    >
      <FormProvider {...methods}>
        <Stack gap="density-xl">
          {agentProp ? (
            <Stack gap="density-xs">
              <Text kind="body/semibold/lg">{agentProp}</Text>
              {noDeploymentError && (
                <Text kind="body/regular/sm" className="text-[var(--text-color-feedback-danger)]">
                  {noDeploymentError}
                </Text>
              )}
            </Stack>
          ) : (
            <ControlledSelect
              useControllerProps={{ control, name: 'agent' }}
              loading={isAgentsLoading}
              items={agents.flatMap((agent) =>
                agent.name ? [{ value: agent.name, children: agent.name }] : []
              )}
              formFieldProps={{
                slotLabel: 'Agent',
                slotError: agentFieldError,
                status: agentFieldError ? 'error' : undefined,
              }}
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
                  <Stack gap="density-sm">
                    <CardSelect
                      label="Eval config template"
                      value={exampleKey}
                      onChange={(key) => setValue('exampleKey', key, { shouldValidate: true })}
                      options={EVAL_CONFIG_SAMPLES.map((sample) => ({
                        value: sample.key,
                        title: sample.displayName,
                        description: sample.description,
                      }))}
                    />
                    <Text kind="body/regular/md" color="secondary">
                      Learn more about{' '}
                      <Anchor
                        kind="inline"
                        textKind="body/regular/md"
                        href={LINK_EVAL_DOCS_APPROACHES}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Dataset-Driven vs Task-Driven evaluation
                      </Anchor>
                      .
                    </Text>
                  </Stack>
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
                      slotHelp: 'Saves a reusable eval-config.json you can select for future runs.',
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
