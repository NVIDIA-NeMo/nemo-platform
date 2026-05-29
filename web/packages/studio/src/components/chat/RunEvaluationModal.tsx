// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormModal } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Block, Stack, Text } from '@nvidia/foundations-react-core';
import { useCallback, useState, type FC } from 'react';

interface RunEvaluationModalProps {
  open: boolean;
  onClose: () => void;
  workspace: string;
  /** URNs of models currently in the Playground panels (deduped, non-null). */
  modelUrns: string[];
}

const EVAL_SETS = [
  { id: 'customer-support-golden', name: 'Customer-Support Golden Set (200 prompts)' },
  { id: 'internal-helpfulness-bench', name: 'Internal Helpfulness Bench (mini)' },
  { id: 'reasoning-subset', name: 'NeMo Eval — Reasoning Subset' },
];

const METRICS = [
  { id: 'llm-judge', name: 'LLM-as-judge (helpfulness)' },
  { id: 'exact-match', name: 'Exact-match accuracy' },
  { id: 'rouge', name: 'ROUGE-L overlap' },
];

/**
 * V1 stub of the Run Evaluation handoff. We don't actually wire this to the
 * Evaluator backend yet — the user picks an eval set + metric, we toast a
 * synthetic job id, and a future PR replaces the body of submit() with a real
 * POST to /apis/agents/v2/.../jobs/evaluate (see SubmitEvaluationModal for
 * the exact payload shape).
 */
export const RunEvaluationModal: FC<RunEvaluationModalProps> = ({
  open,
  onClose,
  workspace,
  modelUrns,
}) => {
  const toast = useToast();
  const [evalSetId, setEvalSetId] = useState(EVAL_SETS[0].id);
  const [metricId, setMetricId] = useState(METRICS[0].id);
  const [submitting, setSubmitting] = useState(false);

  const submit = useCallback(async () => {
    setSubmitting(true);
    await new Promise((r) => setTimeout(r, 350));
    const jobId = `eval-${Date.now().toString(36)}`;
    toast.success(`Evaluation submitted — ${jobId} (would open Evaluations)`);
    setSubmitting(false);
    onClose();
  }, [onClose, toast]);

  return (
    <FormModal
      open={open}
      onClose={onClose}
      title="Run Evaluation"
      submitButtonText="Submit Evaluation"
      onSubmit={submit}
      disabled={submitting || modelUrns.length === 0}
      loading={submitting}
    >
      <Stack gap="density-xl">
        <Block>
          <Text kind="label/bold/sm" color="secondary">
            Models from this Playground ({modelUrns.length})
          </Text>
          {modelUrns.length === 0 ? (
            <Text kind="body/regular/sm" color="secondary">
              Pick at least one model in the Playground first.
            </Text>
          ) : (
            <ul className="mt-2 list-disc pl-5">
              {modelUrns.map((u) => (
                <li key={u} className="text-sm font-mono">
                  {u}
                </li>
              ))}
            </ul>
          )}
        </Block>
        <Block>
          <Text kind="label/bold/sm" color="secondary">
            Eval set
          </Text>
          <select
            className="mt-1 w-full rounded border border-base bg-surface-sunken px-2 py-1 text-sm"
            value={evalSetId}
            onChange={(e) => setEvalSetId(e.target.value)}
          >
            {EVAL_SETS.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </Block>
        <Block>
          <Text kind="label/bold/sm" color="secondary">
            Metric
          </Text>
          <select
            className="mt-1 w-full rounded border border-base bg-surface-sunken px-2 py-1 text-sm"
            value={metricId}
            onChange={(e) => setMetricId(e.target.value)}
          >
            {METRICS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Block>
        <Text kind="body/regular/sm" color="secondary">
          Workspace: <Text kind="body/semibold/sm">{workspace}</Text>
        </Text>
      </Stack>
    </FormModal>
  );
};
