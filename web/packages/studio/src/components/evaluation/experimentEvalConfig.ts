// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { createEvaluation, filesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import type { ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { buildEvalJobName } from '@studio/components/evaluation/submitEvaluationJob';

/** Experiment metadata key holding the name of the fileset that stores its eval config.
 *  Metadata values are plain strings, which is all a fileset name needs to be. */
export const EVAL_CONFIG_FILESET_KEY = 'eval_config_fileset';

/** Flat filename the reusable config is stored as inside its fileset. Every Experiment's
 *  fileset must carry one at the root — there is no per-run file picker. */
export const EVAL_CONFIG_FILENAME = 'eval-config.json';

/** The fileset an Experiment stores its eval config in, or null when it names none. */
export const experimentFilesetName = (experiment: ExperimentResponse): string | null =>
  experiment.metadata?.[EVAL_CONFIG_FILESET_KEY] ?? null;

/** Why an Experiment cannot be run against, or null when it can. Two ways to be invalid:
 *  it names no fileset, or the fileset it names has no eval-config.json at the root. */
export const experimentConfigError = async (
  workspace: string,
  experiment: ExperimentResponse,
  signal?: AbortSignal
): Promise<string | null> => {
  const filesetName = experimentFilesetName(experiment);
  if (!filesetName) {
    return `Experiment "${experiment.name}" has no eval config fileset. Pick another experiment, or create one from a template.`;
  }
  const files = await filesListFilesetFiles(workspace, filesetName, undefined, signal).catch(
    () => null
  );
  if (!files) {
    return `Could not read fileset "${filesetName}" for experiment "${experiment.name}". Pick another experiment.`;
  }
  const hasConfig = (files.data ?? []).some((file) => file.path === EVAL_CONFIG_FILENAME);
  return hasConfig
    ? null
    : `Fileset "${filesetName}" has no ${EVAL_CONFIG_FILENAME} at its root, so experiment "${experiment.name}" cannot be run. Pick another experiment.`;
};

/** Create the Intake Evaluation this run publishes under, returning its **name** —
 *  which is what ``publication.intake.evaluation_id`` takes (the entity id is not it).
 *  ``experimentId`` conversely is the Experiment's **id**, not its name. */
export const createRunEvaluation = async (
  workspace: string,
  {
    experimentId,
    experimentName,
    filesetName,
    signal,
  }: {
    experimentId: string;
    experimentName: string;
    filesetName: string;
    signal?: AbortSignal;
  }
): Promise<string> => {
  // Same normalisation as the job name, so the pair reads as one run.
  const name = buildEvalJobName(experimentName);
  await createEvaluation(
    workspace,
    { name, experiment_ids: [experimentId], dataset_name: filesetName },
    signal
  );
  return name;
};
