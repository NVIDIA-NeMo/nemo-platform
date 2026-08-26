// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getEntityNameError } from '@nemo/common/src/utils/entityName';
import { validateFileFormat } from '@nemo/common/src/utils/fileValidation';
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
import {
  Anchor,
  FormField,
  SegmentedControl,
  Stack,
  Text,
  Upload,
} from '@nvidia/foundations-react-core';
import { submitAgentEvalJob } from '@studio/api/evaluation/agent-evaluations';
import { isConflictError } from '@studio/api/evaluation/eval-config-fileset';
import {
  createRunEvaluation,
  EVAL_CONFIG_FILENAME,
  evaluationConfigError,
  evaluationFilesetName,
} from '@studio/components/evaluation/experimentEvalConfig';
import { JudgeModelSelect } from '@studio/components/evaluation/JudgeModelSelect';
import {
  bareName,
  buildAgentEvalRequestBody,
  buildDatasetEvalRequestBody,
  type DatasetEvalSpec,
  type EvalSpec,
  filesetNameForExperiment,
  injectJudgeModel,
  isDatasetEvalSpec,
  generateEvalConfigName,
  MODE_DEFAULT,
  MODE_EXPERIMENT,
  parseEvalConfig,
  parseUploadedDatasetConfig,
} from '@studio/components/evaluation/submitEvaluationJob';
import { LINK_EVAL_DOCS, LINK_EVAL_DOCS_APPROACHES } from '@studio/constants/links';
import { useJudgeModels } from '@studio/hooks/evaluation/useJudgeModels';
import { getAgentEvaluationsTabRoute } from '@studio/routes/utils';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useRef, useState } from 'react';
import { FormProvider, type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const EVAL_CONFIG_MODE_ITEMS = [
  { value: MODE_DEFAULT, children: 'Create experiment' },
  { value: MODE_EXPERIMENT, children: 'Use existing evaluation' },
];

const DATASET_FILENAME = 'dataset.jsonl';

/** Backend caps page_size at 100; the picker shows the most recent page. */
const LIST_PAGE_SIZE = 100;

const NO_EVALUATIONS_MESSAGE =
  'No evaluations with a reusable eval config yet. Create one to run and re-use it.';

const submitEvaluationBaseSchema = z.object({
  agent: z.string().min(1, 'Agent is required'),
  judgeModel: z.string(),
  mode: z.enum([MODE_DEFAULT, MODE_EXPERIMENT]),
  /** Name of the experiment to create in "Create experiment" mode. The fileset holding this
   *  run's eval-config.json and dataset is derived from it. */
  newName: z.string(),
  /** Name of the existing evaluation whose eval config is reused in "Use existing evaluation" mode. */
  evaluationName: z.string(),
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
      // The derived fileset name is validated too — it is longer, so a name that is legal on
      // its own can still overflow once "-data" is appended, and there is no fileset field to
      // correct it in.
      const nameError =
        getEntityNameError(data.newName.trim()) ??
        getEntityNameError(filesetNameForExperiment(data.newName.trim()), 'Derived fileset name');
      if (nameError) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: nameError,
          path: ['newName'],
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
  newName: generateEvalConfigName(),
  evaluationName: '',
});

/** A file the user picked, plus why it was rejected when it was. */
interface FilePick {
  file: File;
  error?: string;
}

/** The picked eval config, with its parsed spec once it validates. */
interface ConfigPick extends FilePick {
  spec?: DatasetEvalSpec;
}

/** Reject anything that is not one JSON value per line. ``validateFileFormat`` reports a
 *  pretty-printed JSON document as valid ``json``, but the dataset is stored under a fixed
 *  ``dataset.jsonl`` name and referenced as such, so accepting one would only fail at job time. */
const datasetFileError = async (file: File): Promise<string | undefined> => {
  const result = await validateFileFormat(file);
  if (!result.isValid) return result.error ?? 'File is not valid JSON or JSONL';
  if (result.format === 'json' && (await file.text()).trim().includes('\n')) {
    return `${DATASET_FILENAME} must be JSON Lines: one JSON object per line.`;
  }
  return undefined;
};

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

/** The two files the user uploaded in "Create experiment" mode, already validated. */
interface UploadedEvalInputs {
  dataset: File;
  spec: DatasetEvalSpec;
}

/** Resolves the persisted yardstick spec for this submission. In "Create experiment" mode
 *  it takes the uploaded config, bakes in the picked judge and a ref to the dataset that is
 *  about to be uploaded beside it, and seeds both into a new fileset; in "Use existing
 *  evaluation" mode it reads the saved spec back verbatim (no re-bake, no judge re-pick). */
const loadPersistedSpec = async (
  workspace: string,
  formData: SubmitEvaluationFormData,
  configFileset: string | null,
  uploads: UploadedEvalInputs | null
): Promise<EvalSpec> => {
  if (formData.mode === MODE_DEFAULT) {
    if (!uploads) throw new Error('Upload a dataset and an eval config before submitting');
    const signal = new AbortController().signal;
    const name = filesetNameForExperiment(formData.newName.trim());
    const judgeModel = formData.judgeModel || null;
    const spec: DatasetEvalSpec = {
      ...uploads.spec,
      dataset: `${workspace}/${name}#${DATASET_FILENAME}`,
      metrics: judgeModel
        ? uploads.spec.metrics.map((m) => injectJudgeModel(m, judgeModel))
        : uploads.spec.metrics,
    };

    try {
      await filesCreateFileset(workspace, { name, description: 'Agent Evaluation Config' }, signal);
    } catch (err) {
      if (isConflictError(err)) {
        throw new Error(
          `A fileset named "${name}" already exists — choose a different experiment name`
        );
      }
      throw err;
    }
    try {
      await filesUploadFile(workspace, name, DATASET_FILENAME, uploads.dataset, signal);
      await filesUploadFile(
        workspace,
        name,
        EVAL_CONFIG_FILENAME,
        new Blob([JSON.stringify(spec, null, 2)], { type: 'application/json' }),
        signal
      );
    } catch (uploadErr) {
      throw await discardSeeded(workspace, { filesetName: name }, uploadErr);
    }
    return spec;
  }
  if (!configFileset) throw new Error('The selected evaluation has no eval config fileset');
  const blob = await filesDownloadFile(
    workspace,
    configFileset,
    EVAL_CONFIG_FILENAME,
    new AbortController().signal
  );
  if (!blob) throw new Error("Failed to read the selected evaluation's eval config");
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

  const [datasetPick, setDatasetPick] = useState<FilePick | null>(null);
  const [configPick, setConfigPick] = useState<ConfigPick | null>(null);

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

  const agentFieldError = errors.agent?.message;
  const newName = useWatch({ control, name: 'newName' });
  const evaluationName = useWatch({ control, name: 'evaluationName' });

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

  const uploads: UploadedEvalInputs | null =
    datasetPick?.file && !datasetPick.error && configPick?.spec && !configPick.error
      ? { dataset: datasetPick.file, spec: configPick.spec }
      : null;

  const canSubmit =
    mode === MODE_DEFAULT
      ? !!uploads
      : !isValidatingEvaluation && !!selectedEvaluation && !evaluationConfigIssue;

  const judgeMetric = configPick?.spec?.metrics.find(
    (metric) => metric.metric_type === 'llm-judge'
  );

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

  // Both handlers clear first: validation is async, and leaving the previous pick in place
  // would keep the submit gate open against a file the user has already replaced.
  const handleDatasetPicked = async (item: { file: File }) => {
    setDatasetPick(null);
    setDatasetPick({ file: item.file, error: await datasetFileError(item.file) });
  };

  // A fresh config also means a fresh judge: the preselect effect above bails once judgeModel
  // is set, so leaving it would keep the previous file's judge.
  const handleConfigPicked = async (item: { file: File }) => {
    setValue('judgeModel', '');
    setConfigPick(null);
    try {
      setConfigPick({ file: item.file, spec: parseUploadedDatasetConfig(await item.file.text()) });
    } catch (err) {
      setConfigPick({
        file: item.file,
        error: err instanceof Error ? err.message : 'Could not read the file',
      });
    }
  };

  const {
    mutateAsync: submitEvaluation,
    error: submitError,
    isPending,
    reset: resetMutation,
  } = useMutation({
    mutationFn: async (formData: SubmitEvaluationFormData) => {
      const spec = await loadPersistedSpec(workspace, formData, evaluationFileset, uploads);

      const isNew = formData.mode === MODE_DEFAULT;
      const filesetName = isNew
        ? filesetNameForExperiment(formData.newName.trim())
        : (evaluationFileset ?? '');

      const seeded: SeededEntities = isNew ? { filesetName } : {};

      try {
        // "Create experiment" creates a fresh ExperimentGroup to hold this run; "Use existing
        // evaluation" reuses the picked evaluation's group(s) and records the lineage.
        let experimentIds: string[];
        let nameStem: string;
        let parentEvaluationId: string | undefined;
        if (isNew) {
          const experiment = await createExperiment(workspace, { name: formData.newName.trim() });
          seeded.experimentName = experiment.name;
          experimentIds = [experiment.id];
          nameStem = experiment.name;
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
    if (open) return;
    resetForm(makeDefaultValues(agentProp));
    setDatasetPick(null);
    setConfigPick(null);
  }, [open, agentProp, resetForm]);

  // Seed the locked agent on open. A blanket reset here would clobber the judge-model
  // preselect above, which runs earlier in effect order.
  useEffect(() => {
    if (open && agentProp) setValue('agent', agentProp);
  }, [open, agentProp, setValue]);

  const resetAndClose = () => {
    resetMutation();
    resetForm(makeDefaultValues(agentProp));
    setDatasetPick(null);
    setConfigPick(null);
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
                  clearErrors('evaluationName');
                }}
                items={EVAL_CONFIG_MODE_ITEMS}
              />

              {mode === MODE_DEFAULT ? (
                <>
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'newName' }}
                    selectOnFocus
                    formFieldProps={{
                      slotLabel: 'Experiment Name',
                      slotHelp: `Groups this run and future ones against the same config. Its ${EVAL_CONFIG_FILENAME} and dataset are stored in a fileset named "${filesetNameForExperiment(newName.trim() || '<name>')}".`,
                      slotError: errors.newName?.message,
                    }}
                  />

                  <Text kind="label/bold/sm" color="secondary">
                    Select evaluation set
                  </Text>
                  <Text kind="body/regular/md" color="secondary">
                    Learn more about evaluation set requirements in the{' '}
                    <Anchor
                      kind="inline"
                      textKind="body/regular/md"
                      href={LINK_EVAL_DOCS_APPROACHES}
                      target="_blank"
                      rel="noreferrer"
                    >
                      evaluation documentation
                    </Anchor>
                    .
                  </Text>

                  <Upload
                    accept=".jsonl"
                    onValueChange={handleDatasetPicked}
                    onFileRemove={() => setDatasetPick(null)}
                    status={datasetPick?.error ? 'error' : undefined}
                    renderInput={(slotInput) => (
                      <FormField
                        name="dataset"
                        required
                        slotLabel="Add dataset"
                        slotHelp={`Uploaded as ${DATASET_FILENAME}. One JSON object per line.`}
                        slotError={datasetPick?.error}
                        status={datasetPick?.error ? 'error' : undefined}
                      >
                        {slotInput}
                      </FormField>
                    )}
                  >
                    JSON Lines (.jsonl)
                  </Upload>

                  <Upload
                    accept=".json"
                    onValueChange={handleConfigPicked}
                    onFileRemove={() => setConfigPick(null)}
                    status={configPick?.error ? 'error' : undefined}
                    renderInput={(slotInput) => (
                      <FormField
                        name="evalConfig"
                        required
                        slotLabel="Select evaluator config"
                        slotHelp={`Uploaded as ${EVAL_CONFIG_FILENAME}. The dataset reference and judge model below are overwritten for this run.`}
                        slotError={configPick?.error}
                        status={configPick?.error ? 'error' : undefined}
                      >
                        {slotInput}
                      </FormField>
                    )}
                  >
                    Dataset-driven eval config (.json)
                  </Upload>

                  {isLlmJudge && (
                    <JudgeModelSelect<SubmitEvaluationFormData>
                      formFieldName="judgeModel"
                      slotLabel="Model for LLM evaluators"
                    />
                  )}
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
