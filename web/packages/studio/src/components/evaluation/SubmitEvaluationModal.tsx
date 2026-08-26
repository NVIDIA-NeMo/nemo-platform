// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getEntityNameError } from '@nemo/common/src/utils/entityName';
import { useAgentsListAgents } from '@nemo/sdk/generated/agents/api';
import { evaluatorCreateEvaluateJob } from '@nemo/sdk/generated/evaluator/api';
import type {
  AgentEvaluateJobRequest,
  EvaluateJobRequest,
} from '@nemo/sdk/generated/evaluator/schema';
import {
  createExperiment,
  deleteEvaluation,
  deleteExperiment,
  filesCreateFileset,
  filesDeleteFileset,
  filesDownloadFile,
  filesUploadFile,
  useListEvaluations,
  useListExperiments,
} from '@nemo/sdk/generated/platform/api';
import { Anchor, SegmentedControl, Stack, Text } from '@nvidia/foundations-react-core';
import { submitAgentEvalJob } from '@studio/api/evaluation/agent-evaluations';
import { isConflictError, type EvalSeedFile } from '@studio/api/evaluation/eval-config-fileset';
import { EvalFilePickerField } from '@studio/components/evaluation/EvalFilePickerField';
import {
  createRunEvaluation,
  EVAL_CONFIG_FILENAME,
  evaluationConfigError,
  evaluationFilesetName,
} from '@studio/components/evaluation/experimentEvalConfig';
import { JudgeModelSelect } from '@studio/components/evaluation/JudgeModelSelect';
import {
  applyDatasetEvalOverrides,
  bareName,
  buildAgentEvalRequestBody,
  buildDatasetEvalRequestBody,
  buildEvalJobName,
  type DatasetEvalSpec,
  datasetEvalConfigError,
  type EvalSpec,
  isDatasetEvalSpec,
  generateEvalConfigName,
  MODE_DEFAULT,
  MODE_EXPERIMENT,
  parseEvalConfig,
} from '@studio/components/evaluation/submitEvaluationJob';
import { LINK_EVAL_DOCS } from '@studio/constants/links';
import { useJudgeModels } from '@studio/hooks/evaluation/useJudgeModels';
import { getAgentEvaluationsTabRoute } from '@studio/routes/utils';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect } from 'react';
import { FormProvider, type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Create new evaluation' },
  { value: MODE_EXPERIMENT, children: 'Create from existing evaluation' },
];

/** What the two pickers accept. The config mirrors the platform CLI's ``--spec-file``
 *  (JSON or YAML); the dataset mirrors the row formats the evaluator reads. */
const CONFIG_FILE_ACCEPT = '.yaml,.yml,.json';
const DATASET_FILE_ACCEPT = '.jsonl,.json,.csv';

/** Stand-in dataset ref for the pre-submit readiness check. The real ref needs the fileset
 *  that submit creates, and the check only asks whether a dataset will be present at all. */
const PENDING_DATASET_REF = 'pending://uploaded-dataset';

const TASK_CONFIG_UNSUPPORTED =
  'This is a task-driven config. Upload a dataset-driven config (one with "dataset" and "metrics") to run it here.';

/** Backend caps page_size at 100; the picker shows the most recent page. */
const LIST_PAGE_SIZE = 100;

const NO_EVALUATIONS_MESSAGE =
  'No evaluations with a reusable eval config yet. Create one to run and re-use it.';

const submitEvaluationBaseSchema = z.object({
  agent: z.string().min(1, 'Agent is required'),
  /** Optional override for the model every llm-judge metric in the config scores with. */
  judgeModel: z.string(),
  mode: z.enum([MODE_DEFAULT, MODE_EXPERIMENT]),
  /** Experiment created in "Create new evaluation" mode; groups runs for comparison. */
  experimentName: z.string(),
  /** Names this run, and stems the fileset holding its eval-config.json and data files. */
  runName: z.string(),
  /** The uploaded NeMo Evaluator config. Required in "Create new evaluation" mode. */
  configFile: z.instanceof(File).optional(),
  /** Optional dataset uploaded alongside it, overriding the config's own `dataset`. */
  datasetFile: z.instanceof(File).optional(),
  /** Optional override for the config's `prompt_template`. */
  promptTemplate: z.string(),
  /** Name of the existing evaluation whose eval config is reused in reuse mode. */
  evaluationName: z.string(),
});

type SubmitEvaluationFormData = z.infer<typeof submitEvaluationBaseSchema>;

/** Judge model is deliberately not required: an uploaded config may already name one, and
 *  the picker only overrides it. Whether the run has everything it needs is decided against
 *  the parsed config by `datasetEvalConfigError`, not here. */
const submitEvaluationSchema = submitEvaluationBaseSchema.superRefine((data, ctx) => {
  if (data.mode === MODE_DEFAULT) {
    const names = [
      ['experimentName', data.experimentName],
      ['runName', data.runName],
    ] as const;
    for (const [path, value] of names) {
      const nameError = getEntityNameError(value.trim());
      if (nameError) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: nameError, path: [path] });
      }
    }
    if (!data.configFile) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Upload an evaluator config to run',
        path: ['configFile'],
      });
    }
  }
  if (data.mode === MODE_EXPERIMENT && !data.evaluationName) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Pick an evaluation to reuse',
      path: ['evaluationName'],
    });
  }
});

const makeDefaultValues = (agent?: string): SubmitEvaluationFormData => ({
  agent: agent ?? '',
  judgeModel: '',
  mode: MODE_DEFAULT,
  experimentName: generateEvalConfigName(),
  runName: generateEvalConfigName(),
  configFile: undefined,
  datasetFile: undefined,
  promptTemplate: '',
  evaluationName: '',
});

interface SubmitEvaluationModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  /** When provided, pre-fills + locks the agent selector. */
  agent?: string;
  /** Called after a successful submission with the new job's name. */
  onSubmitted?: (jobName: string) => void;
}

interface SeededEntities {
  filesetName?: string;
  experimentName?: string;
  evaluationName?: string;
}

/** Undo what a failed submit created, and return the error to raise.
 *
 *  Deleting the Experiment soft-deletes the Evaluations whose only membership was that group, so
 *  the evaluation is only deleted on its own when the experiment pre-existed this submit and is
 *  therefore being kept. Names are freed either way, since the API renames on delete. When a
 *  delete itself fails the returned error names what to remove by hand. */
const discardSeeded = async (
  workspace: string,
  seeded: SeededEntities,
  cause: unknown
): Promise<unknown> => {
  const leftovers: string[] = [];
  const signal = new AbortController().signal;
  if (seeded.experimentName) {
    await deleteExperiment(workspace, seeded.experimentName, signal).catch(() =>
      leftovers.push(`experiment "${seeded.experimentName}"`)
    );
  } else if (seeded.evaluationName) {
    await deleteEvaluation(workspace, seeded.evaluationName, signal).catch(() =>
      leftovers.push(`evaluation "${seeded.evaluationName}"`)
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

/** Content type for an uploaded dataset, by extension. The evaluator reads the rows itself;
 *  this only labels the blob so the fileset preview renders it as the right kind of file. */
const datasetMimeType = (filename: string): string =>
  filename.toLowerCase().endsWith('.csv') ? 'text/csv' : 'application/jsonl';

/** Resolve the spec this submission runs, and persist it for later reuse.
 *
 *  In "Create new evaluation" mode the uploaded config is parsed (JSON or YAML), the form's
 *  overrides are layered on, and the result is written to a fresh fileset alongside any
 *  uploaded dataset. What lands in `eval-config.json` is the *resolved* spec — real dataset
 *  ref, chosen judge model, overridden prompt — so reusing this evaluation later replays what
 *  actually ran. In reuse mode the saved spec is read back verbatim. */
const loadPersistedSpec = async (
  workspace: string,
  formData: SubmitEvaluationFormData,
  configFileset: string | null,
  filesetName: string
): Promise<EvalSpec> => {
  if (formData.mode !== MODE_DEFAULT) {
    if (!configFileset) throw new Error('The selected evaluation has no eval config fileset');
    const blob = await filesDownloadFile(
      workspace,
      configFileset,
      EVAL_CONFIG_FILENAME,
      new AbortController().signal
    );
    if (!blob) throw new Error("Failed to read the selected evaluation's eval config");
    return parseEvalConfig(await blob.text(), EVAL_CONFIG_FILENAME);
  }

  const signal = new AbortController().signal;
  const { configFile, datasetFile } = formData;
  if (!configFile) throw new Error('Upload an evaluator config to run');

  const authored = parseEvalConfig(await configFile.text(), configFile.name);
  if (!isDatasetEvalSpec(authored)) throw new Error(TASK_CONFIG_UNSUPPORTED);

  const files: EvalSeedFile[] = [];
  let datasetRef: string | undefined;
  if (datasetFile) {
    files.push({
      path: datasetFile.name,
      content: await datasetFile.text(),
      type: datasetMimeType(datasetFile.name),
    });
    datasetRef = `${workspace}/${filesetName}#${datasetFile.name}`;
  }

  const spec = applyDatasetEvalOverrides(authored, {
    dataset: datasetRef,
    promptTemplate: formData.promptTemplate,
    judgeModel: formData.judgeModel || null,
  });
  const configError = datasetEvalConfigError(spec);
  if (configError) throw new Error(configError);

  files.push({
    path: EVAL_CONFIG_FILENAME,
    content: JSON.stringify(spec, null, 2),
    type: 'application/json',
  });

  try {
    await filesCreateFileset(
      workspace,
      { name: filesetName, description: 'Agent Evaluation Config' },
      signal
    );
  } catch (err) {
    if (isConflictError(err)) {
      throw new Error(
        `A fileset named "${filesetName}" already exists — choose a different evaluation name`
      );
    }
    throw err;
  }
  try {
    for (const f of files) {
      await filesUploadFile(
        workspace,
        filesetName,
        f.path,
        new Blob([f.content], { type: f.type }),
        signal
      );
    }
  } catch (uploadErr) {
    throw await discardSeeded(workspace, { filesetName }, uploadErr);
  }
  return spec;
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

  const { data: agentsResponse, isLoading: isAgentsLoading } = useAgentsListAgents(
    workspace,
    undefined,
    { query: { enabled: open && !agentProp } }
  );
  const agents = agentsResponse?.data ?? [];

  const methods = useForm<SubmitEvaluationFormData>({
    resolver: zodResolver(submitEvaluationSchema),
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

  const agentFieldError = errors.agent?.message;
  const evaluationName = useWatch({ control, name: 'evaluationName' });
  const configFile = useWatch({ control, name: 'configFile' });
  const datasetFile = useWatch({ control, name: 'datasetFile' });
  const promptTemplate = useWatch({ control, name: 'promptTemplate' });
  const judgeModel = useWatch({ control, name: 'judgeModel' });

  const { data: evaluationsResponse, isLoading: isEvaluationsLoading } = useListEvaluations(
    workspace,
    // Scope the "use existing evaluation" list to the current agent. agent_name matches against
    // the Evaluation's denormalized agent_names (populated from ingested span telemetry), so an
    // evaluation only appears once it has runs tagged with this agent. selectedAgent is seeded
    // from the agentProp on the agent detail page and set by the in-modal picker otherwise.
    {
      page_size: LIST_PAGE_SIZE,
      sort: '-created_at',
      ...(selectedAgent ? { filter: { agent_name: selectedAgent } } : {}),
    },
    { query: { enabled: open && mode === MODE_EXPERIMENT } }
  );
  const evaluations = evaluationsResponse?.data ?? [];
  /* The eval-config.json is identified on each Evaluation by convention in Studio.
   * It's not persisted by the CLI or API at all. Only Studio created jobs will
   * have this field written to the Evaluation's metadata (dict[str,str]).
   * Unfortunately there's no existing way for Evaluations to be matched to the
   * artifacts that generated them by contract. */
  const compatibleEvaluations = evaluations.filter((item) => evaluationFilesetName(item) != null);
  const selectedEvaluation = evaluations.find((item) => item.name === evaluationName);
  const hasNoEvaluations =
    mode === MODE_EXPERIMENT && !isEvaluationsLoading && !compatibleEvaluations.length;
  const latestEvaluationName = compatibleEvaluations[0]?.name;

  // Parent ExperimentGroups, loaded in reuse mode only to resolve a selected evaluation's group
  // name — so a reused run is named after its experiment (flat) instead of nesting the prior
  // run's random suffix. Used for the name stem only, not for the dropdown or the filter.
  const { data: experimentGroupsResponse } = useListExperiments(
    workspace,
    { page_size: LIST_PAGE_SIZE, sort: '-created_at' },
    { query: { enabled: open && mode === MODE_EXPERIMENT } }
  );
  const experimentGroups = experimentGroupsResponse?.data ?? [];

  useEffect(() => {
    if (mode !== MODE_EXPERIMENT || evaluationName || !latestEvaluationName) return;
    setValue('evaluationName', latestEvaluationName, { shouldValidate: true });
  }, [mode, evaluationName, latestEvaluationName, setValue]);

  const { data: evaluationConfigIssue, isFetching: isValidatingEvaluation } = useQuery({
    queryKey: ['evaluation-eval-config', workspace, evaluationName],
    queryFn: ({ signal }) =>
      selectedEvaluation ? evaluationConfigError(workspace, selectedEvaluation, signal) : null,
    enabled: open && mode === MODE_EXPERIMENT && !!selectedEvaluation,
  });

  const evaluationFileset = selectedEvaluation ? evaluationFilesetName(selectedEvaluation) : null;
  const evaluationFieldError = errors.evaluationName?.message ?? evaluationConfigIssue ?? undefined;

  // Parse the uploaded config as soon as it's picked, so a bad file, an unsupported shape, or
  // a missing dataset/prompt is reported on the field rather than after a submit round-trip.
  // Keyed on the file's identity, not its contents — re-picking a file re-reads it.
  const {
    data: uploadedConfig,
    error: configParseError,
    isFetching: isParsingConfig,
  } = useQuery({
    queryKey: [
      'uploaded-eval-config',
      configFile?.name,
      configFile?.size,
      configFile?.lastModified,
    ],
    queryFn: async () => parseEvalConfig(await configFile!.text(), configFile!.name),
    enabled: open && mode === MODE_DEFAULT && !!configFile,
    retry: false,
    staleTime: Infinity,
  });

  const datasetConfig: DatasetEvalSpec | null =
    uploadedConfig && isDatasetEvalSpec(uploadedConfig) ? uploadedConfig : null;

  // What the run would submit, given the overrides entered so far. The dataset ref is a
  // stand-in because the real one needs the fileset submit creates.
  const resolvedConfig = datasetConfig
    ? applyDatasetEvalOverrides(datasetConfig, {
        dataset: datasetFile ? PENDING_DATASET_REF : undefined,
        promptTemplate,
        judgeModel: judgeModel || null,
      })
    : null;

  const configFieldError =
    errors.configFile?.message ??
    (configParseError instanceof Error ? configParseError.message : undefined) ??
    (uploadedConfig && !datasetConfig ? TASK_CONFIG_UNSUPPORTED : undefined) ??
    (resolvedConfig ? (datasetEvalConfigError(resolvedConfig) ?? undefined) : undefined);

  // With no config picked yet, submit stays enabled so the click surfaces the required-field
  // error on the picker; once one is picked it must actually be runnable.
  const canSubmit =
    mode === MODE_EXPERIMENT
      ? !isValidatingEvaluation && !!selectedEvaluation && !evaluationConfigIssue
      : !isParsingConfig && (!configFile || (!!datasetConfig && !configFieldError));

  const judgeMetric = datasetConfig?.metrics.find((metric) => metric.metric_type === 'llm-judge');

  const defaultModelRef =
    typeof judgeMetric?.payload.metric.model === 'string'
      ? judgeMetric.payload.metric.model
      : undefined;

  // Fetch judge models eagerly so they're ready when a config naming one is picked.
  const { data: judgeModels } = useJudgeModels({ enabled: open });

  // Pre-select the model the uploaded config already names, so the picker shows what will run
  // rather than looking unset. Uses getValues (not a reactive watch) to avoid re-running on
  // every model change — a pick the user made themselves is never overwritten.
  useEffect(() => {
    if (!open || !defaultModelRef || !judgeModels?.length) return;
    if (getValues('judgeModel')) return;
    const target = bareName(defaultModelRef);
    const match = judgeModels.find((m) => m.name === target);
    if (match) {
      const urn = getURNFromNamedEntityRef(match);
      if (urn) setValue('judgeModel', urn);
    }
  }, [open, defaultModelRef, judgeModels, getValues, setValue]);

  const {
    mutateAsync: submitEvaluation,
    error: submitError,
    isPending,
    reset: resetMutation,
  } = useMutation({
    mutationFn: async (formData: SubmitEvaluationFormData) => {
      const isNew = formData.mode === MODE_DEFAULT;
      // The fileset carries its own random suffix rather than being named by the user: it is
      // an artifact of this run, and deriving it from the evaluation name alone would 409 the
      // second time that name is reused.
      const filesetName = isNew
        ? buildEvalJobName(formData.runName.trim())
        : (evaluationFileset ?? '');

      const spec = await loadPersistedSpec(workspace, formData, evaluationFileset, filesetName);

      const seeded: SeededEntities = isNew ? { filesetName } : {};

      try {
        // "Create new evaluation" creates a fresh ExperimentGroup to hold this run; "Create
        // from existing evaluation" reuses the picked evaluation's group(s) and records lineage.
        let experimentIds: string[];
        let nameStem: string;
        let parentEvaluationId: string | undefined;
        if (isNew) {
          const experiment = await createExperiment(workspace, {
            name: formData.experimentName.trim(),
          });
          seeded.experimentName = experiment.name;
          experimentIds = [experiment.id];
          nameStem = formData.runName.trim();
        } else {
          if (!selectedEvaluation) throw new Error('No evaluation to reuse');
          experimentIds = selectedEvaluation.experiment_ids;
          // Name the run after its parent experiment (group), not the prior run — else the run's
          // random suffix would nest and grow on every reuse. Fall back to the eval name with a
          // trailing 8-char suffix stripped if the group isn't in the loaded page.
          const parentGroup = experimentGroups.find(
            (group) => group.id === selectedEvaluation.experiment_ids[0]
          );
          nameStem = parentGroup?.name ?? selectedEvaluation.name.replace(/-[a-z0-9]{8}$/, '');
          parentEvaluationId = selectedEvaluation.id;
        }

        const evaluationId = await createRunEvaluation(workspace, {
          experimentIds,
          nameStem,
          filesetName,
          parentEvaluationId,
        });
        seeded.evaluationName = evaluationId;

        const selections = {
          workspace,
          agent: formData.agent,
          filesetName,
          experimentName: nameStem,
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
        return { name: created.name };
      } catch (err) {
        throw await discardSeeded(workspace, seeded, err);
      }
    },
    onSuccess: ({ name }, formData) => {
      toast.success(`Evaluation "${name}" submitted`);
      void queryClient.invalidateQueries({ queryKey: ['evaluator-jobs', workspace] });
      onSubmitted?.(name);
      resetAndClose();
      navigate(getAgentEvaluationsTabRoute(workspace, bareName(formData.agent)));
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
      submitDisabled={!canSubmit}
      // An uploaded config and dataset live only in form state; a stray backdrop click
      // would discard both with nothing to restore them from. Close and Cancel remain.
      dismissible={false}
      loading={isPending}
      errorText={errorMessage}
      className="w-[690px]! max-w-[95vw]!"
    >
      <FormProvider {...methods}>
        <Stack gap="density-xl">
          {agentProp ? (
            <Text kind="body/regular/md">
              Run evaluation via NeMo Evaluator&apos;s built-in runner. Evaluator also supports
              Harbor and Gym as runners.{' '}
              <Anchor
                kind="inline"
                textKind="body/regular/md"
                href={LINK_EVAL_DOCS}
                target="_blank"
                rel="noreferrer"
              >
                Learn more
              </Anchor>
              .
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
                slotError: agentFieldError,
                status: agentFieldError ? 'error' : undefined,
              }}
            />
          )}

          {selectedAgent ? (
            <Stack gap="density-xl">
              <SegmentedControl
                className="w-full [&_button]:flex-1"
                value={mode}
                onValueChange={(v) => {
                  setValue('mode', v as typeof MODE_DEFAULT | typeof MODE_EXPERIMENT, {
                    shouldValidate: false,
                  });
                  clearErrors('evaluationName');
                }}
                items={EVAL_CONFIG_MODE_ITEMS}
              />

              {mode === MODE_DEFAULT ? (
                <>
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'experimentName' }}
                    selectOnFocus
                    required
                    formFieldProps={{
                      slotLabel: 'Experiment name',
                      slotHelp: 'Groups multiple evaluation runs together for comparison.',
                      slotError: errors.experimentName?.message,
                    }}
                  />
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'runName' }}
                    selectOnFocus
                    required
                    formFieldProps={{
                      slotLabel: 'Evaluation name',
                      slotHelp:
                        'The name of the evaluation you are testing, e.g. "Baseline evaluation run".',
                      slotError: errors.runName?.message,
                    }}
                  />

                  <Stack gap="density-sm">
                    <Text kind="label/bold/lg">Dataset and metrics</Text>
                    <Text kind="label/regular/md" color="secondary">
                      Upload a NeMo Evaluator configuration.{' '}
                      <Anchor
                        kind="inline"
                        textKind="label/regular/md"
                        href={LINK_EVAL_DOCS}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Learn more
                      </Anchor>
                      .
                    </Text>
                  </Stack>

                  <EvalFilePickerField
                    useControllerProps={{ control, name: 'configFile' }}
                    accept={CONFIG_FILE_ACCEPT}
                    label="Evaluator config"
                    placeholder="Select a JSON or YAML config"
                    required
                    formFieldProps={{
                      slotError: configFieldError,
                      status: configFieldError ? 'error' : undefined,
                    }}
                  />

                  <Stack gap="density-lg">
                    <Text kind="label/regular/md" color="secondary">
                      Optional configuration overrides
                    </Text>
                    <EvalFilePickerField
                      useControllerProps={{ control, name: 'datasetFile' }}
                      accept={DATASET_FILE_ACCEPT}
                      label="Add dataset"
                      placeholder="Select a .jsonl, .json or .csv file"
                      slotHelp="Replaces the config's own dataset reference."
                    />
                    <ControlledTextInput
                      useControllerProps={{ control, name: 'promptTemplate' }}
                      placeholder="{{ item.question }}"
                      formFieldProps={{
                        slotLabel: 'Prompt template',
                        slotHelp:
                          "Jinja rendered against each dataset row. Replaces the config's own prompt_template.",
                        slotError: errors.promptTemplate?.message,
                      }}
                    />
                    <JudgeModelSelect<SubmitEvaluationFormData>
                      formFieldName="judgeModel"
                      slotLabel="Model for LLM evaluators"
                      placeholder="Select a model to get started"
                    />
                  </Stack>
                </>
              ) : (
                <>
                  {hasNoEvaluations ? (
                    <Text kind="body/regular/md" color="secondary">
                      {NO_EVALUATIONS_MESSAGE}
                    </Text>
                  ) : (
                    <ControlledSelect
                      useControllerProps={{ control, name: 'evaluationName' }}
                      loading={isEvaluationsLoading}
                      items={compatibleEvaluations.flatMap((item) =>
                        item.name ? [{ value: item.name, children: item.name }] : []
                      )}
                      formFieldProps={{
                        slotLabel: 'Evaluation',
                        slotHelp: `Reuses the selected evaluation's ${EVAL_CONFIG_FILENAME}.`,
                        slotError: evaluationFieldError,
                        status: evaluationFieldError ? 'error' : undefined,
                      }}
                    />
                  )}
                </>
              )}
            </Stack>
          ) : null}
        </Stack>
      </FormProvider>
    </FormModal>
  );
};
