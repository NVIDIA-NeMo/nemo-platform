// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { createEvaluation, filesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import type { EvaluationResponse } from '@nemo/sdk/generated/platform/schema';
import { buildEvalJobName } from '@studio/components/evaluation/submitEvaluationJob';

/** Evaluation metadata key holding the name of the fileset that stores its eval config.
 *  Lives on the Evaluation, not its ExperimentGroup: the config is a property of a single
 *  run, and the Evaluation entity's ``metadata`` is documented for exactly this "config
 *  snapshot". Metadata values are plain strings, which is all a fileset name needs to be. */
export const EVAL_CONFIG_FILESET_KEY = 'eval_config_fileset';

/** Flat filename the reusable config is stored as inside its fileset. Every reusable
 *  evaluation's fileset carries one at the root — there is no per-run file picker. */
export const EVAL_CONFIG_FILENAME = 'eval-config.json';

/** The fileset an Evaluation stores its eval config in, or null when it names none. */
export const evaluationFilesetName = (evaluation: EvaluationResponse): string | null =>
  evaluation.metadata?.[EVAL_CONFIG_FILESET_KEY] ?? null;

/** Why an Evaluation cannot be reused, or null when it can. Two ways to be invalid:
 *  it names no fileset, or the fileset it names has no eval-config.json at the root. */
export const evaluationConfigError = async (
  workspace: string,
  evaluation: EvaluationResponse,
  signal?: AbortSignal
): Promise<string | null> => {
  const filesetName = evaluationFilesetName(evaluation);
  if (!filesetName) {
    return `Evaluation "${evaluation.name}" has no eval config fileset. Pick another evaluation, or create one from a template.`;
  }
  const files = await filesListFilesetFiles(workspace, filesetName, undefined, signal).catch(
    () => null
  );
  if (!files) {
    return `Could not read fileset "${filesetName}" for evaluation "${evaluation.name}". Pick another evaluation.`;
  }
  const hasConfig = (files.data ?? []).some((file) => file.path === EVAL_CONFIG_FILENAME);
  return hasConfig
    ? null
    : `Fileset "${filesetName}" has no ${EVAL_CONFIG_FILENAME} at its root, so evaluation "${evaluation.name}" cannot be reused. Pick another evaluation.`;
};

/** Create the Intake Evaluation this run publishes under, returning its **name** —
 *  which is what ``publication.intake.evaluation_id`` takes (the entity id is not it).
 *  The eval-config fileset pointer is written to the Evaluation's own ``metadata`` (the
 *  documented "config snapshot" home) so a later run can reuse it; ``parentEvaluationId``
 *  records the evaluation this one was derived from, when reusing an existing one. */
export const createRunEvaluation = async (
  workspace: string,
  {
    experimentIds,
    nameStem,
    filesetName,
    parentEvaluationId,
    signal,
  }: {
    experimentIds: string[];
    nameStem: string;
    filesetName: string;
    parentEvaluationId?: string;
    signal?: AbortSignal;
  }
): Promise<string> => {
  const name = buildEvalJobName(nameStem);
  await createEvaluation(
    workspace,
    {
      name,
      experiment_ids: experimentIds,
      dataset_name: filesetName,
      metadata: { [EVAL_CONFIG_FILESET_KEY]: filesetName },
      ...(parentEvaluationId ? { parent_evaluation_id: parentEvaluationId } : {}),
    },
    signal
  );
  return name;
};
