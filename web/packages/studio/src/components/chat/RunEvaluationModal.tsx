// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormModal } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { FormField, Select, Stack, Text } from '@nvidia/foundations-react-core';
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
 * V1 stub of the Run Evaluation handoff. The backend endpoint exists
 * (`agentsCreateJob`) but Studio isn't wired to it yet. Rather than fake a
 * success, we surface an honest "coming next" toast and close — see Follow-up
 * A in the staged-seahorse plan. A future PR replaces submit() with a real
 * POST and routes the user to the eval-job detail page.
 */
export const RunEvaluationModal: FC<RunEvaluationModalProps> = ({ open, onClose, modelUrns }) => {
  const toast = useToast();
  const [evalSetId, setEvalSetId] = useState(EVAL_SETS[0].id);
  const [metricId, setMetricId] = useState(METRICS[0].id);
  const [submitting, setSubmitting] = useState(false);

  const submit = useCallback(async () => {
    setSubmitting(true);
    toast.info(
      `Coming next — Studio will POST this evaluation to the agents service in the next release. (Captured: ${modelUrns.length} model${modelUrns.length === 1 ? '' : 's'} · eval-set ${evalSetId} · metric ${metricId})`
    );
    setSubmitting(false);
    onClose();
  }, [evalSetId, metricId, modelUrns.length, onClose, toast]);

  return (
    <FormModal
      open={open}
      onClose={onClose}
      title="Run Evaluation"
      instruction="Submit saves your choices and previews the evaluator request. Full integration coming next release."
      submitButtonText="Submit Evaluation"
      onSubmit={submit}
      disabled={submitting || modelUrns.length === 0}
      loading={submitting}
    >
      <Stack gap="density-xl" className="pt-density-md">
        <Stack gap="density-sm">
          <Text kind="label/bold/sm">Models from this Playground ({modelUrns.length})</Text>
          {modelUrns.length === 0 ? (
            <Text kind="body/regular/sm" color="secondary">
              Pick at least one model in the Playground first.
            </Text>
          ) : (
            <ul className="list-disc pl-5">
              {modelUrns.map((u) => (
                <li key={u} className="font-mono text-sm">
                  {u}
                </li>
              ))}
            </ul>
          )}
        </Stack>
        <FormField name="eval-set" slotLabel="Eval Set">
          <Select
            multiple={false}
            className="w-full"
            items={EVAL_SETS.map((e) => ({ value: e.id, children: e.name }))}
            value={evalSetId}
            onValueChange={(next) => setEvalSetId(next as string)}
          />
        </FormField>
        <FormField name="metric" slotLabel="Metric">
          <Select
            multiple={false}
            className="w-full"
            items={METRICS.map((m) => ({ value: m.id, children: m.name }))}
            value={metricId}
            onValueChange={(next) => setMetricId(next as string)}
          />
        </FormField>
      </Stack>
    </FormModal>
  );
};
