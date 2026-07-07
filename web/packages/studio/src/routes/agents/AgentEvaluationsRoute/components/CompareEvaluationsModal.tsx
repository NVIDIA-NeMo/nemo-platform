// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { Block, Card, Checkbox, Flex, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import {
  fetchAgentEvalJobs,
  isTerminalStatus,
  type AgentEvalJob,
} from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { getAgentEvaluationCompareRoute } from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type FC } from 'react';
import { useNavigate } from 'react-router-dom';

interface CompareEvaluationsModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  /** The eval config the base job ran against. Only other jobs that ran
   *  against the same config are offered — comparing across configs would
   *  line up scores from different evaluators/datasets. */
  evalConfig: string;
  /** The evaluation the user is comparing from. Always included in the
   *  comparison and excluded from the pick list. */
  baseJob: AgentEvalJob;
}

export const CompareEvaluationsModal: FC<CompareEvaluationsModalProps> = ({
  open,
  onClose,
  workspace,
  evalConfig,
  baseJob,
}) => {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!open) setSelected(new Set());
  }, [open]);

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ['agent-eval-jobs', workspace] as const,
    queryFn: ({ signal }) => fetchAgentEvalJobs(workspace, signal),
    enabled: open && !!workspace,
  });

  // Only terminal jobs that ran against the same eval config, excluding the
  // base job itself — comparison needs finished scores and aligned evaluators.
  const candidates = useMemo(
    () =>
      jobs.filter(
        (job) =>
          job.name !== baseJob.name &&
          job.spec.eval_config === evalConfig &&
          isTerminalStatus(job.status)
      ),
    [jobs, baseJob.name, evalConfig]
  );

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleCompare = () => {
    const names = [baseJob.name, ...candidates.map((c) => c.name).filter((n) => selected.has(n))];
    navigate(getAgentEvaluationCompareRoute(workspace, names));
    onClose();
  };

  return (
    <FormModal
      open={open}
      onClose={onClose}
      title="Compare evaluations"
      instruction={`Select one or more evaluations that ran against "${evalConfig}" to compare side by side with "${baseJob.name}".`}
      submitButtonText={selected.size > 0 ? `Compare ${selected.size + 1} evaluations` : 'Compare'}
      submitDisabled={selected.size === 0}
      onSubmit={(e) => {
        e.preventDefault();
        handleCompare();
      }}
    >
      {isLoading ? (
        <Flex align="center" justify="center" className="min-h-[120px] w-full">
          <Spinner size="small" aria-label="Loading evaluations..." />
        </Flex>
      ) : candidates.length === 0 ? (
        <Block className="text-subtle">
          No other completed evaluations ran against this eval config yet.
        </Block>
      ) : (
        <Stack gap="density-md">
          {candidates.map((job) => (
            <Card key={job.name} className="hover:bg-surface-hover">
              <Flex align="center" gap="density-md">
                <Checkbox
                  checked={selected.has(job.name)}
                  onCheckedChange={() => toggle(job.name)}
                  aria-label={`Compare with ${job.name}`}
                />
                <Stack gap="density-xs" className="flex-1 min-w-0">
                  <Text kind="body/semibold/sm" className="truncate">
                    {job.name}
                  </Text>
                  <Flex gap="density-md" align="center" wrap="wrap">
                    <StatusBadge status={job.status} />
                    {job.spec.agent && (
                      <Text kind="body/regular/sm" color="secondary" className="truncate">
                        {job.spec.agent}
                      </Text>
                    )}
                    <Text kind="body/regular/sm" color="secondary">
                      <RelativeTime datetime={job.created_at} />
                    </Text>
                  </Flex>
                </Stack>
              </Flex>
            </Card>
          ))}
        </Stack>
      )}
    </FormModal>
  );
};
