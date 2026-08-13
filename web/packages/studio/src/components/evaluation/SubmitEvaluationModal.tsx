// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { RadioCard } from '@nemo/common/src/components/RadioCard';
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
  createExperiment,
  deleteExperiment,
  filesCreateFileset,
  filesDeleteFileset,
  filesDownloadFile,
  filesUploadFile,
  useListExperiments,
} from '@nemo/sdk/generated/platform/api';
import {
  Anchor,
  Flex,
  RadioGroupRoot,
  SegmentedControl,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import { submitAgentEvalJob } from '@studio/api/evaluation/agent-evaluations';
import { isConflictError, type EvalSeedFile } from '@studio/api/evaluation/eval-config-fileset';
import {
  createRunEvaluation,
  EVAL_CONFIG_FILENAME,
  EVAL_CONFIG_FILESET_KEY,
  experimentConfigError,
  experimentFilesetName,
} from '@studio/components/evaluation/experimentEvalConfig';
import { JudgeModelSelect } from '@studio/components/evaluation/JudgeModelSelect';
import {
  bareName,
  buildAgentEvalRequestBody,
  buildDatasetEvalRequestBody,
  buildPersistedSpec,
  type EvalSpec,
  filesetNameForExperiment,
  injectJudgeModel,
  type InlineMetricBundle,
  isDatasetEvalSpec,
  generateEvalConfigName,
  MODE_DEFAULT,
  MODE_EXPERIMENT,
  parseEvalConfig,
} from '@studio/components/evaluation/submitEvaluationJob';
import { LINK_EVAL_DOCS_APPROACHES } from '@studio/constants/links';
import {
  DEFAULT_EVAL_CONFIG_KEY,
  EVAL_CONFIG_SAMPLES,
  getEvalConfigSample,
} from '@studio/constants/sampleAgents';
import { useJudgeModels } from '@studio/hooks/evaluation/useJudgeModels';
import {
  getAgentEvaluationDetailRoute,
  getEvaluationResultDetailsRoute,
} from '@studio/routes/utils';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useRef, useState } from 'react';
import { FormProvider, type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Use Example' },
  { value: MODE_EXPERIMENT, children: 'Choose Experiment' },
];

const DATASET_FILENAME = 'dataset.jsonl';

/** Backend caps page_size at 100; the picker shows the most recent page. */
const EXPERIMENT_PAGE_SIZE = 100;
const README_FILENAME = 'README.md';

const NO_DEPLOYMENT_MESSAGE = 'This agent has no active deployment.';
const DEPLOYMENT_CHECK_FAILED_MESSAGE =
  'Could not verify this agent has a running deployment. Try again.';

const submitEvaluationBaseSchema = z.object({
  agent: z.string().min(1, 'Agent is required'),
  judgeModel: z.string(),
  mode: z.enum([MODE_DEFAULT, MODE_EXPERIMENT]),
  exampleKey: z.string(),
  /** Name of the experiment to create in "Use Example" mode. */
  newName: z.string(),
  /** Fileset created alongside it, holding eval-config.json and any data artifacts. */
  filesetName: z.string(),
  /** Name of the experiment to re-run in "Choose Experiment" mode. */
  experimentName: z.string(),
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
      const filesetError = getEntityNameError(data.filesetName.trim());
      if (filesetError) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: filesetError,
          path: ['filesetName'],
        });
      }
    }
    if (data.mode === MODE_EXPERIMENT && !data.experimentName) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Pick an experiment to run',
        path: ['experimentName'],
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

const makeDefaultValues = (agent?: string): SubmitEvaluationFormData => {
  const newName = generateEvalConfigName();
  return {
    agent: agent ?? '',
    judgeModel: '',
    mode: MODE_DEFAULT,
    exampleKey: DEFAULT_EVAL_CONFIG_KEY,
    newName,
    filesetName: filesetNameForExperiment(newName),
    experimentName: '',
  };
};

interface SubmitEvaluationModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  /** When provided, pre-fills + locks the agent selector. */
  agent?: string;
  /** Called after a successful submission with the new job's name. */
  onSubmitted?: (jobName: string) => void;
}

/** Undo what a failed submit created, and return the error to raise.
 *
 *  Everything here is name-unique per workspace, so a leftover holds the name the retry wants:
 *  without this, the second attempt fails on a conflict instead of the original problem.
 *  Deleting the Experiment also soft-deletes the Evaluation created under it (the API cascades
 *  to members whose only membership was that group) and frees both names, so the two deletes
 *  below unwind the whole chain. When a delete itself fails the returned error names what to
 *  remove by hand. */
const discardSeeded = async (
  workspace: string,
  seeded: { filesetName?: string; experimentName?: string },
  cause: unknown
): Promise<unknown> => {
  const leftovers: string[] = [];
  const signal = new AbortController().signal;
  if (seeded.experimentName) {
    await deleteExperiment(workspace, seeded.experimentName, signal).catch(() =>
      leftovers.push(`experiment "${seeded.experimentName}"`)
    );
  }
  if (seeded.filesetName) {
    await filesDeleteFileset(workspace, seeded.filesetName, signal).catch(() =>
      leftovers.push(`fileset "${seeded.filesetName}"`)
    );
  }
  if (leftovers.length === 0) return cause;
  const causeDetail = cause instanceof Error ? cause.message : String(cause);
  return new Error(
    `${causeDetail} — ${leftovers.join(' and ')} could not be removed; delete manually before retrying under the same name.`,
    { cause }
  );
};

/** Resolves the persisted yardstick spec for this submission. In "Use Example" mode
 *  it builds the spec from the sample template (fanning the metric onto every task with
 *  the picked judge baked in) and seeds it into a new fileset; in "Choose Fileset" mode
 *  it reads the saved spec back verbatim (no re-fan, no judge re-pick). */
const loadPersistedSpec = async (
  workspace: string,
  formData: SubmitEvaluationFormData,
  experimentFileset: string | null
): Promise<EvalSpec> => {
  if (formData.mode === MODE_DEFAULT) {
    const signal = new AbortController().signal;
    const name = formData.filesetName.trim();
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
      throw await discardSeeded(workspace, { filesetName: name }, uploadErr);
    }
    return spec;
  }
  // Choose-experiment mode: read the saved spec out of the experiment's own fileset, as-is.
  // The fileset is reached through the experiment, never picked directly, so there is no
  // per-run file choice to make — the config lives at a known path by convention.
  if (!experimentFileset) throw new Error('The selected experiment has no eval config fileset');
  const blob = await filesDownloadFile(
    workspace,
    experimentFileset,
    EVAL_CONFIG_FILENAME,
    new AbortController().signal
  );
  if (!blob) throw new Error("Failed to read the selected experiment's eval config");
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
    clearErrors,
    formState,
  } = methods;
  const { errors } = formState;

  const mode = useWatch({ control, name: 'mode' });
  const selectedAgent = useWatch({ control, name: 'agent' });

  const {
    data: runningDeployments,
    isLoading: isDeploymentsLoading,
    isError: isDeploymentsError,
  } = useAgentsListDeployments(workspace, runningDeploymentsQuery(selectedAgent), {
    query: { enabled: open && Boolean(selectedAgent) },
  });

  const hasRunningDeployment = (runningDeployments?.data ?? []).length > 0;

  const deploymentVerified =
    Boolean(selectedAgent) && !isDeploymentsLoading && !isDeploymentsError && hasRunningDeployment;

  const deploymentError = ((): string | undefined => {
    if (!selectedAgent || isDeploymentsLoading) return undefined;
    if (isDeploymentsError) return DEPLOYMENT_CHECK_FAILED_MESSAGE;
    if (!hasRunningDeployment) return NO_DEPLOYMENT_MESSAGE;
    return undefined;
  })();

  const agentFieldError = errors.agent?.message ?? deploymentError;
  const exampleKey = useWatch({ control, name: 'exampleKey' });
  const experimentName = useWatch({ control, name: 'experimentName' });

  // Experiments to re-run. There is no "metadata key exists" filter, so the ones without a
  // config fileset can only be excluded after the fact — see experimentConfigError below.
  const { data: experimentsResponse, isLoading: isExperimentsLoading } = useListExperiments(
    workspace,
    { page_size: EXPERIMENT_PAGE_SIZE, sort: '-created_at' },
    { query: { enabled: open && mode === MODE_EXPERIMENT } }
  );
  const experiments = experimentsResponse?.data ?? [];
  const selectedExperiment = experiments.find((item) => item.name === experimentName);

  // Validate on selection rather than at submit: a bad pick should be obvious before the user
  // commits, and the check is two cheap reads.
  const { data: experimentConfigIssue, isFetching: isValidatingExperiment } = useQuery({
    queryKey: ['experiment-eval-config', workspace, experimentName],
    queryFn: ({ signal }) =>
      selectedExperiment ? experimentConfigError(workspace, selectedExperiment, signal) : null,
    enabled: open && mode === MODE_EXPERIMENT && !!selectedExperiment,
  });

  const experimentFileset = selectedExperiment ? experimentFilesetName(selectedExperiment) : null;
  const experimentFieldError = errors.experimentName?.message ?? experimentConfigIssue ?? undefined;

  // Hold submit while the pick is still being checked, so a bad experiment cannot slip through
  // the gap between selecting it and the validation landing.
  const canRunSelectedExperiment =
    mode !== MODE_EXPERIMENT ||
    (!isValidatingExperiment && !!selectedExperiment && !experimentConfigIssue);

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
      const spec = await loadPersistedSpec(workspace, formData, experimentFileset);

      // Order is forced by the backend: the fileset is seeded above, then the Experiment must
      // exist before an Evaluation can reference it, and the Evaluation before the job can
      // publish to it — the worker creates neither.
      const isNew = formData.mode === MODE_DEFAULT;
      const filesetName = isNew ? formData.filesetName.trim() : (experimentFileset ?? '');

      // What this submit created, so a failure rolls back exactly that and nothing pre-existing.
      const seeded: { filesetName?: string; experimentName?: string } = isNew
        ? { filesetName }
        : {};

      try {
        const experiment = isNew
          ? await createExperiment(workspace, {
              name: formData.newName.trim(),
              metadata: { [EVAL_CONFIG_FILESET_KEY]: filesetName },
            })
          : selectedExperiment;
        if (!experiment) throw new Error('No experiment to run this evaluation under');
        if (isNew) seeded.experimentName = experiment.name;

        const evaluationId = await createRunEvaluation(workspace, {
          experimentId: experiment.id,
          experimentName: experiment.name,
          filesetName,
        });

        const selections = {
          workspace,
          agent: formData.agent,
          filesetName,
          experimentName: experiment.name,
          evaluationId,
        };
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
      } catch (err) {
        // Re-running an existing experiment seeds nothing, so there is nothing to unwind: its
        // fileset predates this submit and its Evaluation is reused by the retry.
        throw await discardSeeded(workspace, seeded, err);
      }
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
      submitDisabled={!deploymentVerified || !canRunSelectedExperiment}
      loading={isPending}
      errorText={errorMessage}
      className="w-[690px]! max-w-[95vw]!"
    >
      <FormProvider {...methods}>
        <Stack gap="density-xl">
          {agentProp ? (
            <Stack gap="density-xs">
              <Text kind="body/semibold/lg">{agentProp}</Text>
              {deploymentError && (
                <Text kind="body/regular/sm" className="text-[var(--text-color-feedback-danger)]">
                  {deploymentError}
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
                  setValue('mode', v as typeof MODE_DEFAULT | typeof MODE_EXPERIMENT, {
                    shouldValidate: false,
                  });
                  clearErrors('experimentName');
                }}
                items={EVAL_CONFIG_MODE_ITEMS}
              />

              {mode === MODE_DEFAULT ? (
                <>
                  <Stack gap="density-sm">
                    <RadioGroupRoot
                      name="eval-config-template"
                      orientation="horizontal"
                      className="w-full"
                      aria-label="Eval config template"
                      value={exampleKey}
                      onValueChange={(key) => setValue('exampleKey', key, { shouldValidate: true })}
                    >
                      <Flex gap="density-md" className="w-full *:flex-1">
                        {EVAL_CONFIG_SAMPLES.map((sample) => (
                          <RadioCard
                            key={sample.key}
                            value={sample.key}
                            label={sample.displayName}
                            description={sample.description}
                            showIndicator={false}
                          />
                        ))}
                      </Flex>
                    </RadioGroupRoot>
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
                      slotLabel: 'New Experiment Name',
                      slotHelp:
                        'Groups this run and future ones against the same config. Select it later to re-run.',
                      slotError: errors.newName?.message,
                    }}
                  />
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'filesetName' }}
                    selectOnFocus
                    formFieldProps={{
                      slotLabel: 'Fileset Name',
                      slotHelp: `Stores this experiment's ${EVAL_CONFIG_FILENAME} and any data files.`,
                      slotError: errors.filesetName?.message,
                    }}
                  />
                </>
              ) : (
                <ControlledSelect
                  useControllerProps={{ control, name: 'experimentName' }}
                  loading={isExperimentsLoading}
                  items={experiments.flatMap((item) =>
                    item.name ? [{ value: item.name, children: item.name }] : []
                  )}
                  formFieldProps={{
                    slotLabel: 'Experiment',
                    slotHelp: `Runs the ${EVAL_CONFIG_FILENAME} in the experiment's fileset.`,
                    slotError: experimentFieldError,
                    status: experimentFieldError ? 'error' : undefined,
                  }}
                />
              )}
            </Stack>
          ) : null}
        </Stack>
      </FormProvider>
    </FormModal>
  );
};
