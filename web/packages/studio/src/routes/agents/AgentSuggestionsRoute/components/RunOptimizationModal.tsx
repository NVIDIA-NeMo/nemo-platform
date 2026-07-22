// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledSearchableSelect } from '@nemo/common/src/components/form/ControlledSearchableSelect';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getAgentsListOptimizeJobsQueryKey,
  useAgentsCreateOptimizeJob,
  useAgentsListAgents,
} from '@nemo/sdk/generated/agents/api';
import { Banner, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { isExternalEndpointAgent } from '@studio/routes/agents/agentTypes';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useMemo } from 'react';
import { type SubmitHandler, useForm } from 'react-hook-form';
import { z } from 'zod';

const optimizationFormSchema = z.object({
  agent: z.string().min(1, 'Agent is required'),
  optimizeConfigPath: z
    .string()
    .trim()
    .min(1, 'Optimization config path is required')
    .refine((path) => path.startsWith('/'), 'Enter an absolute platform path'),
  jobName: z
    .string()
    .trim()
    .refine(
      (name) => name.length === 0 || /^[a-zA-Z0-9_.-]+$/.test(name),
      'Use only letters, digits, dots, hyphens, and underscores'
    ),
});

type OptimizationFormData = z.infer<typeof optimizationFormSchema>;

const DEFAULT_VALUES: OptimizationFormData = {
  agent: '',
  optimizeConfigPath: '',
  jobName: '',
};

interface RunOptimizationModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  onSubmitted?: (jobName: string) => void;
}

export const RunOptimizationModal: FC<RunOptimizationModalProps> = ({
  open,
  onClose,
  workspace,
  onSubmitted,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const agentsQuery = useAgentsListAgents(
    workspace,
    { page: 1, page_size: 100 },
    { query: { enabled: open && !!workspace } }
  );
  const agents = useMemo(() => agentsQuery.data?.data ?? [], [agentsQuery.data?.data]);
  const externalAgentCount = agents.filter(isExternalEndpointAgent).length;
  const agentOptions = useMemo(
    () =>
      agents
        .filter((agent) => !isExternalEndpointAgent(agent))
        .flatMap((agent) => (agent.name ? [{ value: agent.name, label: agent.name }] : []))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [agents]
  );
  const {
    mutateAsync: createOptimizeJob,
    error: submitError,
    isPending,
    reset: resetMutation,
  } = useAgentsCreateOptimizeJob();
  const {
    control,
    handleSubmit,
    reset: resetForm,
  } = useForm<OptimizationFormData>({
    resolver: zodResolver(optimizationFormSchema),
    defaultValues: DEFAULT_VALUES,
    disabled: isPending,
    mode: 'onSubmit',
    reValidateMode: 'onChange',
  });

  const resetAndClose = () => {
    resetMutation();
    resetForm(DEFAULT_VALUES);
    onClose();
  };

  const onSubmit: SubmitHandler<OptimizationFormData> = async (formData) => {
    try {
      const job = await createOptimizeJob({
        workspace,
        data: {
          name: formData.jobName.trim() || undefined,
          description: `Hyperparameter tuning for ${formData.agent}`,
          spec: {
            agent: formData.agent,
            optimize_config: formData.optimizeConfigPath.trim(),
            workspace,
          },
        },
      });
      toast.success(`Hyperparameter tuning "${job.name}" submitted`);
      void queryClient.invalidateQueries({
        queryKey: getAgentsListOptimizeJobsQueryKey(workspace),
      });
      onSubmitted?.(job.name);
      resetAndClose();
    } catch {
      // The mutation error is rendered in the modal.
    }
  };

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      title="Tune Hyperparameters"
      instruction="Run NAT optimization against a registered agent. The optimization YAML defines the search space, dataset, evaluator, and objective."
      submitButtonText="Start tuning"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={
        submitError
          ? getErrorMessage(submitError as Error, 'Failed to submit hyperparameter tuning')
          : undefined
      }
      className="w-[min(40rem,calc(100vw-2rem))]"
    >
      <Banner kind="inline" status="info">
        The current backend accepts an absolute YAML path available to the platform job. Browser
        uploads and fileset-backed optimization configs are not supported yet.
      </Banner>
      {externalAgentCount > 0 && (
        <Banner kind="inline" status="warning">
          External endpoint agents are not listed here because the current optimizer cannot apply
          per-trial hyperparameters to a remote service. Use Agent Evaluations for those agents.
        </Banner>
      )}
      <ControlledSearchableSelect
        useControllerProps={{ control, name: 'agent' }}
        options={agentOptions}
        isLoading={agentsQuery.isLoading}
        triggerPlaceholder="Select an agent"
        searchPlaceholder="Search agents..."
        emptyMessage={agentsQuery.isLoading ? 'Loading agents...' : 'No registered agents found.'}
        formFieldProps={{ slotLabel: 'Agent' }}
      />
      <ControlledTextInput
        useControllerProps={{ control, name: 'optimizeConfigPath' }}
        label="Optimization YAML path"
        placeholder="/workspace/configs/support-agent-optimize.yml"
        required
      />
      <Text kind="body/regular/xs" color="secondary">
        Hyperparameter sweeps affect platform-managed agents because the optimizer loads their NAT
        workflow in-process. Remote endpoint agents do not receive per-trial parameter changes.
      </Text>
      <ControlledTextInput
        useControllerProps={{ control, name: 'jobName' }}
        label="Job name (optional)"
        placeholder="support-agent-hpo"
      />
    </FormModal>
  );
};
