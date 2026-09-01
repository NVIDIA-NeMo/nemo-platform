// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  PlatformJobStepStatusResponse,
  PlatformJobTaskStatusResponse,
} from '@nemo/sdk/generated/customizer/schema';
import { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import type { CustomizationJob } from '@studio/util/customizationBackend';

/**
 * A customization job's failure, assembled from the step/task status tree.
 *
 * The useful text lives at `steps[].tasks[].error_details`: the training runner maps raw
 * exceptions through `services/rl/.../errors/error_rules.yaml` into `{message, type, detail}`
 * before reporting them, but that payload is written at *task* level and the jobs dispatcher
 * only propagates `status_details` up to the job. So the job's own `error_details` is a copy of
 * the failing step's, which for Kubernetes is generic infrastructure text.
 */
export interface CustomizationFailure {
  /** Best available user-facing text. Never empty. */
  message: string;
  /** Mapped exception class, e.g. `CudaError`. Absent for infrastructure failures. */
  errorType?: string;
  /** Raw exception line, `f"{type(exc).__name__}: {exc}"`. */
  detail?: string;
  /** Container terminated message, or the tail of its logs. Task level only. */
  errorStack?: string;
  /** Display form of the failing pipeline step's raw name, e.g. `GRPO training`. */
  failingStepLabel?: string;
  /** True when only generic infrastructure text was available — no mapped cause was found. */
  isGeneric: boolean;
}

const FALLBACK_MESSAGE = 'The customization job failed.';

/**
 * Infrastructure text that carries no cause. These are not failure modes we can explain, they are
 * what the Kubernetes/Volcano/Docker backends write when a pod dies — and the pod reconciler can
 * overwrite a task's mapped message with one of them (it replaces `error_details` wholesale, and
 * an `error -> error` transition is permitted). Classifying them lets the resolver keep looking
 * rather than surfacing "Pod X is in error state" over a real explanation sitting one level up.
 */
const GENERIC_MESSAGE_PATTERNS: readonly RegExp[] = [
  /^one or more tasks are in error state/i,
  /^job has errored pods/i,
  /^pod .+ is in error state$/i,
  /^job failed\.?$/i,
  /^job not found$/i,
  /^job exited with non-zero code \d+/i,
  /^job exited with code \d+/i,
];

const isGenericMessage = (message: string): boolean =>
  GENERIC_MESSAGE_PATTERNS.some((pattern) => pattern.test(message.trim()));

/**
 * `error_details` and `status_details` are `Record<string, unknown>` on the wire — the OpenAPI
 * schema declares them as free-form objects, so every read needs narrowing.
 */
const readString = (
  bag: Record<string, unknown> | null | undefined,
  key: string
): string | undefined => {
  const value = bag?.[key];
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined;
};

/** Pipeline steps emitted by the RL, automodel and unsloth compilers. */
const STEP_LABELS: Record<string, string> = {
  'model-dataset-environment-download': 'model, dataset & environment download',
  'model-and-dataset-download': 'model & dataset download',
  'grpo-training': 'GRPO training',
  'dpo-training': 'DPO training',
  training: 'training',
  'model-upload': 'model upload',
  'model-entity-creation': 'model entity creation',
};

/** Known steps read as prose; anything new degrades to its de-kebabed name rather than vanishing. */
export const formatPipelineStepName = (step: string): string =>
  STEP_LABELS[step] ?? step.replace(/[-_]+/g, ' ').trim();

const isErrored = (status: PlatformJobStatus | undefined): boolean =>
  status === PlatformJobStatus.error;

/**
 * Prefers a task whose message actually explains something. The trainer and the pod reconciler
 * both write to the same task record, so a step can hold one task with a mapped cause and another
 * with boilerplate; picking the explanatory one first is what makes the banner useful.
 */
const findFailingTask = (
  step: PlatformJobStepStatusResponse | undefined
): PlatformJobTaskStatusResponse | undefined => {
  const tasks = step?.tasks ?? [];
  const errored = tasks.filter((task) => isErrored(task.status));
  const explains = (task: PlatformJobTaskStatusResponse) => {
    const message = readString(task.error_details, 'message');
    return message !== undefined && !isGenericMessage(message);
  };
  const hasMessage = (task: PlatformJobTaskStatusResponse) =>
    readString(task.error_details, 'message') !== undefined;

  return (
    errored.find(explains) ??
    errored.find(hasMessage) ??
    // A step can be marked errored before its tasks' statuses catch up, so a task still reported
    // as active can be the one holding the mapped message. Checked before falling back to an
    // errored-but-silent task, which would otherwise strand that message.
    tasks.find(explains) ??
    tasks.find(hasMessage) ??
    // Nothing explains itself; keep the errored task anyway for its error_stack.
    errored[0]
  );
};

/**
 * Resolves what to tell the user about a failed customization job.
 *
 * Returns `undefined` unless the job is in `error` — a cancelled job is not a failure, and a
 * running one has nothing to report yet.
 *
 * Message candidates are tried most- to least-specific, and the first *non-generic* one wins.
 * Falling through on generic text is deliberate: it recovers the mapped cause when the pod
 * reconciler has clobbered the task record, and it degrades cleanly on the multi-node GRPO path,
 * where the Volcano backend never sets `error_details` at all and `status_details.message` is the
 * only text that exists.
 */
export const resolveCustomizationFailure = (
  job: CustomizationJob | undefined,
  steps: PlatformJobStepStatusResponse[] = []
): CustomizationFailure | undefined => {
  if (!job || !isErrored(job.status)) {
    return undefined;
  }

  const failingStep = steps.find((step) => isErrored(step.status));
  const failingTask = findFailingTask(failingStep);

  const candidates = [
    readString(failingTask?.error_details, 'message'),
    readString(failingStep?.error_details, 'message'),
    readString(failingStep?.status_details, 'message'),
    readString(job.error_details, 'message'),
    readString(job.status_details, 'message'),
  ].filter((candidate): candidate is string => candidate !== undefined);

  const specific = candidates.find((candidate) => !isGenericMessage(candidate));
  const message = specific ?? candidates[0] ?? FALLBACK_MESSAGE;

  return {
    message,
    errorType: readString(failingTask?.error_details, 'type'),
    detail: readString(failingTask?.error_details, 'detail'),
    errorStack: failingTask?.error_stack?.trim() ? failingTask.error_stack : undefined,
    failingStepLabel: failingStep ? formatPipelineStepName(failingStep.name) : undefined,
    isGeneric: specific === undefined,
  };
};
