// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MODE_DEFAULT, MODE_EXPERIMENT } from '@studio/components/evaluation/submitEvaluationJob';

/** One screen of the Run Evaluation wizard. */
export type WizardStep = 'start' | 'experiment' | 'source' | 'evaluation';

export type EvaluationMode = typeof MODE_DEFAULT | typeof MODE_EXPERIMENT;

/**
 * The screens a run passes through, decided by the answer to the first one.
 *
 * Creating an experiment and re-running an existing evaluation ask for different things, and a
 * single page that shows both sets — most of them irrelevant — is what made the old form hard to
 * read. Splitting the choice out front means each later step only ever shows fields that apply.
 */
export const stepsFor = (mode: EvaluationMode): WizardStep[] =>
  mode === MODE_DEFAULT
    ? ['start', 'experiment', 'evaluation']
    : ['start', 'source', 'evaluation'];

/** Heading shown for each step in the stepper, per path. */
export const stepHeading = (step: WizardStep, mode: EvaluationMode): string => {
  switch (step) {
    case 'start':
      return 'Start';
    case 'experiment':
      return 'Experiment';
    case 'source':
      return 'Evaluation to re-run';
    case 'evaluation':
      return mode === MODE_DEFAULT ? 'Evaluation' : 'New evaluation';
  }
};

/** One-line description under each step's heading. */
export const stepDescription = (step: WizardStep, mode: EvaluationMode): string => {
  switch (step) {
    case 'start':
      return 'How to begin';
    case 'experiment':
      return 'Name and settings';
    case 'source':
      return 'Its config is reused';
    case 'evaluation':
      return mode === MODE_DEFAULT ? 'Name, dataset, config' : 'Name this run';
  }
};

export const stepIndex = (steps: WizardStep[], step: WizardStep): number => steps.indexOf(step);

export const nextStep = (steps: WizardStep[], step: WizardStep): WizardStep =>
  steps[Math.min(stepIndex(steps, step) + 1, steps.length - 1)];

export const previousStep = (steps: WizardStep[], step: WizardStep): WizardStep =>
  steps[Math.max(stepIndex(steps, step) - 1, 0)];

export const isLastStep = (steps: WizardStep[], step: WizardStep): boolean =>
  stepIndex(steps, step) === steps.length - 1;
