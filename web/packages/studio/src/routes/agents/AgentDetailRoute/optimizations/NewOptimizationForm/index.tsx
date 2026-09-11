// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { DEFAULT_DEBOUNCE_MS } from '@nemo/common/src/constants';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { toValidEntityName } from '@nemo/common/src/utils/entityName';
import {
  Banner,
  Button,
  FormField,
  Stack,
  Stepper,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  bareModelName,
  judgeModelUrl,
} from '@studio/routes/agents/AgentDetailRoute/optimizations/judgeModel';
import { AdvancedAccordion } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/AdvancedAccordion';
import { BudgetSection } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/BudgetSection';
import { EvaluationSection } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/EvaluationSection';
import {
  optimizationFormSchema,
  type OptimizationFormOutput,
  type OptimizationFormValues,
} from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/formValues';
import { IntentSection } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/IntentSection';
import { buildOptimizationName } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/optimizationName';
import { optimizationTargets } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/optimizationTargets';
import { RunSummaryPanel } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/RunSummaryPanel';
import { useOptimizationNameCheck } from '@studio/routes/agents/AgentDetailRoute/optimizations/NewOptimizationForm/useOptimizationNameCheck';
import {
  budgetById,
  buildOptimizeConfig,
  intentById,
} from '@studio/routes/agents/AgentDetailRoute/optimizations/optimizeConfig';
import {
  loadStudyDataset,
  STUDY_DATASET_PATH,
} from '@studio/routes/agents/AgentDetailRoute/optimizations/studyDataset';
import { submitOptimization } from '@studio/routes/agents/AgentDetailRoute/optimizations/submitOptimization';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { getWorkspaceJobDetailRoute } from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft } from 'lucide-react';
import { type FC, useEffect, useMemo, useRef, useState } from 'react';
import { FormProvider, useController, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { useDebounce } from 'use-debounce';

const DEFAULT_INTENT = 'accuracy' as const;

export interface NewOptimizationFormProps {
  agentName?: string;
  evals: AgentEvaluationRow[];
  isEvalsPending: boolean;
  /** Returns to the studies table; also the target of the breadcrumb above the header. */
  onBack: () => void;
}

/**
 * Configure and submit a numeric HPO study for one agent.
 *
 * Renders in place of the studies table rather than in a modal: the form carries a live config
 * preview and a run summary beside it, neither of which survives a dialog's width, and its own
 * breadcrumb is what returns to the list.
 *
 * The user answers three questions — what to tune for, what to score against, how many trials —
 * and the YAML is generated from the answers. Nothing here asks for a config path or a fileset;
 * those are staged on submit ({@link submitOptimization}).
 */
export const NewOptimizationForm: FC<NewOptimizationFormProps> = ({
  agentName,
  evals,
  isEvalsPending,
  onBack,
}) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const toast = useToast();
  const [submitError, setSubmitError] = useState<string | undefined>();

  const targets = useMemo(() => optimizationTargets(evals), [evals]);

  const methods = useForm<OptimizationFormValues, unknown, OptimizationFormOutput>({
    resolver: zodResolver(optimizationFormSchema),
    mode: 'onBlur',
    defaultValues: {
      name: agentName ? buildOptimizationName(agentName, DEFAULT_INTENT) : '',
      intent: DEFAULT_INTENT,
      budget: 'standard',
      experimentId: '',
      judgeModel: '',
      searchSpace: intentById(DEFAULT_INTENT).parameters,
    },
  });

  const {
    control,
    watch,
    setValue,
    handleSubmit,
    formState: { errors, touchedFields, isSubmitting },
  } = methods;

  const {
    field: { value: nameValue, onChange: onNameChange, onBlur: onNameBlur },
  } = useController({ control, name: 'name' });

  /** The name is generated so the user never has to invent one. Typing in the field hands it over
   *  for good — after that the generator stops overwriting what they wrote. */
  const [isNameGenerated, setIsNameGenerated] = useState(true);
  const generatedFor = useRef(`${agentName ?? ''}:${DEFAULT_INTENT}`);

  const preview = toValidEntityName(nameValue, '');
  const [debouncedName] = useDebounce(preview, DEFAULT_DEBOUNCE_MS);
  const nameCheck = useOptimizationNameCheck(workspace, debouncedName, preview);

  const intentId = watch('intent');
  const intent = intentById(intentId);
  const budget = budgetById(watch('budget'));
  const searchSpace = watch('searchSpace');
  const experimentId = watch('experimentId');
  const judgeModel = watch('judgeModel');

  // Regenerate when the intent changes, since the intent is part of the name — and when the agent
  // finally resolves, which is what leaves the initial name empty.
  useEffect(() => {
    if (!isNameGenerated || !agentName) return;
    const key = `${agentName}:${intentId}`;
    if (generatedFor.current === key) return;
    generatedFor.current = key;
    setValue('name', buildOptimizationName(agentName, intentId), { shouldValidate: true });
  }, [agentName, intentId, isNameGenerated, setValue]);

  // The most recent evaluation is the one a user almost always means, so seed it — but only once
  // the list has actually arrived, which is after the form's defaults are set.
  useEffect(() => {
    if (!experimentId && targets[0]) {
      setValue('experimentId', targets[0].experimentId, { shouldValidate: true });
    }
  }, [experimentId, targets, setValue]);

  const target = targets.find((candidate) => candidate.experimentId === experimentId);

  // The rows travel with the study rather than being referenced, so they have to be readable before
  // submit — an evaluation whose config Studio cannot parse is a blocking problem, not a run-time
  // one. Keyed by evaluation name so switching experiments refetches.
  const evaluationName = target?.evaluation.name;
  const dataset = useQuery({
    queryKey: ['optimization-study-dataset', workspace, evaluationName],
    queryFn: ({ signal }) => loadStudyDataset(workspace, target!.evaluation, signal),
    enabled: !!workspace && !!target,
    retry: false,
    staleTime: Infinity,
  });

  const datasetError = dataset.error
    ? dataset.error instanceof Error
      ? dataset.error.message
      : 'Could not read this evaluation.'
    : undefined;

  const config = useMemo(
    () =>
      buildOptimizeConfig({
        parameters: searchSpace,
        trials: budget.trials,
        datasetPath: dataset.data ? STUDY_DATASET_PATH : undefined,
        judgeModel: judgeModel ? bareModelName(judgeModel) : undefined,
        judgeModelUrl: judgeModel ? judgeModelUrl(workspace, judgeModel) : undefined,
        experimentId: experimentId || undefined,
      }),
    [searchSpace, budget, dataset.data, judgeModel, workspace, experimentId]
  );

  const nameError =
    nameCheck.status === 'conflict'
      ? `An optimization named ${nameCheck.candidate} already exists`
      : touchedFields.name
        ? errors.name?.message
        : undefined;

  const blockingReason = !agentName
    ? 'No agent selected.'
    : !experimentId
      ? 'Pick an evaluation to score trials against.'
      : datasetError
        ? 'Pick an evaluation whose dataset can be read.'
        : dataset.isPending
          ? 'Reading the evaluation dataset...'
          : !judgeModel
            ? 'Pick a judge model to score trials with.'
            : nameError
              ? 'Fix the name before running.'
              : errors.searchSpace
                ? 'Fix the search space before running.'
                : undefined;

  const onSubmit = handleSubmit(async (values) => {
    // The conflict lives in local state, not `formState.errors`, so the resolver alone would let
    // this through to a request the API can only answer with 409.
    if (!agentName || nameCheck.status === 'conflict' || !dataset.data) return;
    setSubmitError(undefined);
    try {
      const job = await submitOptimization({
        workspace,
        agentName,
        name: values.name,
        config,
        dataset: dataset.data,
      });
      toast.success(`Started optimization ${values.name}.`);
      if (job.name) navigate(getWorkspaceJobDetailRoute(workspace, job.name));
      else onBack();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : 'Could not start the optimization study.'
      );
    }
  });

  return (
    <FormProvider {...methods}>
      <Stack gap="density-xl" className="w-full">
        <Button kind="tertiary" className="w-fit px-0" onClick={onBack}>
          <ChevronLeft className="size-4" aria-hidden />
          Optimizations
        </Button>

        <Stack gap="density-sm">
          <Text kind="title/sm">New optimization</Text>
          <Text kind="body/regular/sm" color="secondary">
            Parameter sweep{agentName ? ` on ${agentName}` : ''}. Choose what to tune for, what to
            score it against, and how hard to look — then run it from here.
          </Text>
        </Stack>

        {submitError && (
          <Banner kind="inline" status="error">
            {submitError}
          </Banner>
        )}

        <div className="grid grid-cols-1 items-start gap-8 xl:grid-cols-[minmax(0,1fr)_380px]">
          <Stack gap="density-2xl">
            <FormField
              slotLabel="Name"
              slotError={nameError}
              slotHelp={
                nameError
                  ? undefined
                  : nameCheck.status === 'checking'
                    ? 'Checking name...'
                    : nameCheck.status === 'failed'
                      ? "Couldn't check name availability. You can still submit."
                      : isNameGenerated
                        ? 'Named for you from the agent and what you are tuning for. Edit it if you want something else.'
                        : preview && (
                            <>
                              Your optimization will be created as{' '}
                              <span className="text-primary">{preview}</span>
                            </>
                          )
              }
              status={nameError ? 'error' : undefined}
            >
              <TextInput
                value={nameValue}
                disabled={isSubmitting}
                status={nameError ? 'error' : undefined}
                onChange={(event) => {
                  setIsNameGenerated(false);
                  onNameChange(event.currentTarget.value);
                }}
                onBlur={onNameBlur}
              />
            </FormField>

            {/* Every step's fields are on screen at once — this is a form, not a wizard — so the
                stepper reads as "what still needs an answer" rather than "where am I". Intent and
                budget both ship a default, which leaves the evaluation as the only step that can
                be outstanding.

                `slotSuccessIndicator` keeps the step number in a completed node, where the
                stepper would otherwise swap in a check. The numbers are how the sections are
                referred to, so they have to survive a step being answered. */}
            <Stepper
              layout="vertical"
              aria-label="Optimization setup"
              activeStep={experimentId && judgeModel ? 3 : 1}
              items={[
                {
                  slotHeading: 'What are you tuning for?',
                  slotDescription: 'Pick one — it sets the objective and the parameters we sweep',
                  slotSuccessIndicator: 1,
                  slotContent: <IntentSection />,
                },
                {
                  slotHeading: 'Test it against',
                  slotDescription: 'Its latest evaluation supplies the dataset and metrics',
                  slotSuccessIndicator: 2,
                  slotContent: (
                    <EvaluationSection
                      targets={targets}
                      selected={target}
                      isLoading={isEvalsPending}
                      datasetRows={dataset.data?.length}
                      isDatasetLoading={!!target && dataset.isPending}
                      datasetError={datasetError}
                    />
                  ),
                },
                {
                  slotHeading: 'How hard should we look?',
                  slotDescription: 'More trials, better odds of a win',
                  slotSuccessIndicator: 3,
                  slotContent: <BudgetSection />,
                },
              ]}
            />

            <AdvancedAccordion searchSpace={searchSpace} config={config} />
          </Stack>

          <RunSummaryPanel
            intent={intent}
            budget={budget}
            searchSpace={searchSpace}
            target={target}
            blockingReason={blockingReason}
            isSubmitting={isSubmitting}
            onRun={() => void onSubmit()}
          />
        </div>
      </Stack>
    </FormProvider>
  );
};
