// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { useAgentsForSelect } from '@iron-swarm/api/agents';
import { useInspectAgent } from '@iron-swarm/api/filesets';
import { ModelGroupFields } from '@iron-swarm/components/ModelGroupFields';
import { parseEnvPairs, splitList } from '@iron-swarm/formValues';
import {
  getIronSwarmListManifestsQueryKey,
  useIronSwarmCreateManifest,
  useIronSwarmGetModelConfigDefaults,
} from '@iron-swarm/generated/api';
import type { WarGameModels } from '@iron-swarm/generated/schema';
import { useBreadcrumbs, useToast, useWorkspace } from '@iron-swarm/host';
import { getIronSwarmManifestListRoute, getIronSwarmRunListRoute } from '@iron-swarm/paths';
import {
  manifestFormSchema,
  type ManifestFormData,
} from '@iron-swarm/routes/NewIronSwarmManifestRoute/schema';
import { AccessibleTitle, AccordionSection, ControlledSelect, ControlledTextInput } from '@nemo/common';
import {
  AccordionRoot,
  Button,
  Flex,
  Panel,
  PageHeader,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { useQueryClient } from '@tanstack/react-query';
import { FC, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router';

export const NewIronSwarmManifestRoute: FC = () => {
  const workspace = useWorkspace();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [models, setModels] = useState<WarGameModels>({});
  const { data: modelDefaults } = useIronSwarmGetModelConfigDefaults(workspace, { query: {} });

  useBreadcrumbs({
    items: [
      { href: getIronSwarmRunListRoute(workspace), slotLabel: 'Iron Swarm' },
      { href: getIronSwarmManifestListRoute(workspace), slotLabel: 'Manifests' },
      { slotLabel: 'New' },
    ],
  });

  const { control, handleSubmit, watch, setError, setValue } = useForm<ManifestFormData>({
    defaultValues: { name: '', agent: '', egress: '', env: '', port: '', secrets: '' },
    resolver: zodResolver(manifestFormSchema),
  });

  // Pre-fill the port + secret fields from the agent's auto-derived defaults when one is selected;
  // both stay editable so the operator can override.
  const selectedAgent = watch('agent');
  const inspectAgent = useInspectAgent();
  const { mutate: runInspectAgent } = inspectAgent;
  useEffect(() => {
    if (!selectedAgent) return;
    runInspectAgent(
      { workspace, agent: selectedAgent },
      {
        onSuccess: (facts) => {
          setValue('port', String(facts.port));
          setValue('secrets', facts.secrets.join(', '));
        },
      }
    );
  }, [selectedAgent, workspace, runInspectAgent, setValue]);

  const { data: agents = [], isLoading: agentsLoading } = useAgentsForSelect(workspace);
  const agentItems = useMemo(
    () =>
      agents.flatMap((agent) => (agent.name ? [{ value: agent.name, children: agent.name }] : [])),
    [agents]
  );

  const createManifest = useIronSwarmCreateManifest({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getIronSwarmListManifestsQueryKey(workspace) });
        toast.success('Manifest created.');
        navigate(getIronSwarmManifestListRoute(workspace));
      },
      onError: () => toast.error('Failed to create the manifest. Check the agent and try again.'),
    },
  });

  const onSubmitAgent = handleSubmit((data) => {
    if (!data.agent) {
      setError('agent', { message: 'Select a deployed agent' });
      return;
    }
    const egress = splitList(data.egress);
    const secrets = splitList(data.secrets);
    const env = parseEnvPairs(data.env);
    const port = data.port ? Number(data.port) : undefined;
    if (port !== undefined && !Number.isInteger(port)) {
      setError('port', { message: 'Enter a whole number' });
      return;
    }
    createManifest.mutate({
      workspace,
      data: {
        name: data.name,
        agent: data.agent,
        ...(egress.length ? { egress } : {}),
        ...(secrets.length ? { secrets } : {}),
        ...(Object.keys(env).length ? { env } : {}),
        ...(port !== undefined ? { port } : {}),
        models,
      },
    });
  });

  return (
    <AccessibleTitle title="New Iron Swarm manifest">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="New Manifest"
          slotDescription="Scaffold a reusable war-game target. Give it an ID, then pick where the agent comes from."
        />
        <Panel className="max-w-[720px]">
          <Stack gap="density-xl" padding="density-lg">
            <ControlledTextInput
              useControllerProps={{ control, name: 'name' }}
              formFieldProps={{
                slotLabel: 'Manifest ID',
                slotHelp: 'Lowercase, e.g. clockbot-hardening.',
              }}
            />

            <form onSubmit={onSubmitAgent}>
                <Stack gap="density-xl">
                  <ControlledSelect
                    useControllerProps={{ control, name: 'agent' }}
                    loading={agentsLoading}
                    items={agentItems}
                    formFieldProps={{ slotLabel: 'Deployed Agent' }}
                  />
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'egress' }}
                    formFieldProps={{
                      slotLabel: 'Egress Allow-list (optional)',
                      slotHelp:
                        'Comma-separated host[:port] for external services the agent calls (e.g. ' +
                        'en.wikipedia.org, raw.githubusercontent.com). Needed when the tool hosts are not ' +
                        'discoverable from the agent config.',
                    }}
                  />
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'port' }}
                    formFieldProps={{
                      slotLabel: 'Victim Port',
                      slotHelp: inspectAgent.isPending
                        ? 'Detecting from the agent…'
                        : 'Auto-detected from the deployment. Edit to override.',
                    }}
                  />
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'secrets' }}
                    formFieldProps={{
                      slotLabel: 'Secret Names',
                      slotHelp: inspectAgent.isPending
                        ? 'Detecting from the agent…'
                        : 'Comma-separated; auto-detected from the agent config. Edit to override.',
                    }}
                  />
                  <ControlledTextInput
                    useControllerProps={{ control, name: 'env' }}
                    formFieldProps={{
                      slotLabel: 'Environment Variables (optional)',
                      slotHelp:
                        'Comma-separated KEY=VALUE for non-secret settings the agent reads. ' +
                        'Credentials belong in Secret Names — values here are stored in plain text.',
                    }}
                  />
                  <AccordionRoot>
                    <AccordionSection value="models" title="Models (optional)">
                      <Stack gap="density-md">
                        <Text kind="body/regular/sm" className="text-subtle">
                          Defaults shown as placeholders; override any group for this target. Each
                          run can still change them.
                        </Text>
                        <ModelGroupFields
                          value={models}
                          onChange={setModels}
                          workspace={workspace}
                          defaults={modelDefaults}
                        />
                      </Stack>
                    </AccordionSection>
                  </AccordionRoot>
                  <Flex gap="density-md">
                    <Button color="brand" type="submit" disabled={createManifest.isPending}>
                      {createManifest.isPending ? 'Creating…' : 'Create Manifest'}
                    </Button>
                    <Button asChild kind="tertiary">
                      <Link to={getIronSwarmManifestListRoute(workspace)}>Cancel</Link>
                    </Button>
                  </Flex>
              </Stack>
            </form>
          </Stack>
        </Panel>
      </Stack>
    </AccessibleTitle>
  );
};
