// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useGuardrailsGetGuardrailConfig } from '@nemo/sdk/generated/platform/api';
import { Badge, Flex, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { useGuardrailCheck } from '@studio/api/guardrail-checks/hooks';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import {
  getCheckInputText,
  getCheckOutputText,
} from '@studio/components/dataViews/GuardrailChecksDataView/checkMessages';
import { getLatestRunStatus } from '@studio/components/dataViews/GuardrailChecksDataView/checkStatus';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { RailResultList } from '@studio/routes/guardrails/GuardrailCheckDetailRoute/RailResultList';
import {
  getGuardrailChecksRoute,
  getGuardrailDetailRoute,
  getGuardrailsRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { ArrowLeft } from 'lucide-react';
import type { FC, ReactNode } from 'react';
import { Link } from 'react-router-dom';

/** Green "Allowed" / red "Guarded" badge for a check's overall verdict. */
const OverallVerdictBadge: FC<{ status: 'success' | 'blocked' | 'unknown' }> = ({ status }) => {
  if (status === 'success') {
    return (
      <Badge color="green" kind="solid">
        Allowed
      </Badge>
    );
  }
  if (status === 'blocked') {
    return (
      <Badge color="red" kind="solid">
        Guarded
      </Badge>
    );
  }
  return (
    <Badge color="gray" kind="solid">
      Unknown
    </Badge>
  );
};

/** A labelled turn in the conversation (User / Assistant). */
const MessageBlock: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <Stack gap="density-xs">
    <Text kind="label/bold/sm" className="text-text-secondary">
      {label}
    </Text>
    <Text className="whitespace-pre-wrap rounded bg-surface-raised p-density-md leading-relaxed">
      {children}
    </Text>
  </Stack>
);

const SectionHeading: FC<{ children: ReactNode }> = ({ children }) => (
  <Text kind="label/bold/sm" className="text-text-secondary uppercase tracking-wide">
    {children}
  </Text>
);

export const GuardrailCheckDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { guardrailConfigName, guardrailCheckName } = useRequiredPathParams([
    ROUTE_PARAMS.guardrailConfigName,
    ROUTE_PARAMS.guardrailCheckName,
  ]);

  const checksRoute = getGuardrailChecksRoute(workspace, guardrailConfigName);

  useBreadcrumbs({
    items: [
      { href: getGuardrailsRoute(workspace), slotLabel: 'Guardrails' },
      {
        href: getGuardrailDetailRoute(workspace, guardrailConfigName),
        slotLabel: guardrailConfigName,
      },
      { slotLabel: guardrailCheckName },
    ],
  });

  const {
    data: config,
    isPending: isConfigPending,
    isError: isConfigError,
  } = useGuardrailsGetGuardrailConfig(workspace, guardrailConfigName, {
    query: { enabled: Boolean(workspace && guardrailConfigName) },
  });

  // Checks are hard children of the config; the name lookup must be scoped by the
  // parent config's entity id, which only exists once the config query resolves.
  const configId = config?.id;
  const {
    data: check,
    isPending: isCheckPending,
    isError: isCheckError,
  } = useGuardrailCheck(workspace, guardrailCheckName, configId ?? '', {
    enabled: Boolean(workspace && guardrailCheckName && configId),
  });

  const backLink = (
    <Link to={checksRoute} className="w-fit">
      <Flex align="center" gap="density-xs" className="text-text-secondary hover:text-text-primary">
        <ArrowLeft size={16} />
        <Text>Back to Checks</Text>
      </Flex>
    </Link>
  );

  if (isConfigPending || isCheckPending) {
    return <Loading description="Loading check..." />;
  }

  if (isConfigError || isCheckError || !config || !check) {
    return (
      <AccessibleTitle title={`Guardrail check ${guardrailCheckName}`}>
        <Stack className="w-full h-full min-h-0 p-density-2xl" gap="density-xl">
          {backLink}
          <PageHeader slotHeading={guardrailCheckName} />
          <Text className="text-feedback-danger">Failed to load guardrail check.</Text>
        </Stack>
      </AccessibleTitle>
    );
  }

  const inputText = getCheckInputText(check.data.messages);
  const outputText = getCheckOutputText(check.data.messages);

  const runs = check.data.runs;
  const latestRun = runs.length ? runs[runs.length - 1] : undefined;
  const overallStatus = getLatestRunStatus(check);

  return (
    <AccessibleTitle title={`Guardrail check ${check.name}`}>
      <Stack className="w-full min-h-full p-density-2xl" gap="density-xl">
        {backLink}

        <PageHeader
          slotHeading={
            <span className="min-w-0 truncate" title={check.name}>
              {check.name}
            </span>
          }
          slotDescription={check.data.description || undefined}
        />

        {/* ── Messages ─────────────────────────────── */}
        <Stack gap="density-md">
          <SectionHeading>Messages</SectionHeading>
          <MessageBlock label="User">{inputText || '—'}</MessageBlock>
          {outputText ? <MessageBlock label="Assistant">{outputText}</MessageBlock> : null}
        </Stack>

        {/* ── Last Run ─────────────────────────────── */}
        <Stack gap="density-md">
          <SectionHeading>Last Run</SectionHeading>

          {latestRun && overallStatus ? (
            <Stack gap="density-md">
              <Flex align="center" justify="between" gap="density-md">
                <Flex align="center" gap="density-sm">
                  <Text className="text-text-secondary">Overall</Text>
                  <OverallVerdictBadge status={overallStatus} />
                </Flex>
                <Text className="text-text-secondary">
                  <RelativeTime datetime={latestRun.run_at} focusableForTooltip={false} />
                </Text>
              </Flex>

              <RailResultList rails={config.data?.rails} run={latestRun} />
            </Stack>
          ) : (
            <Text className="text-text-secondary">No runs yet.</Text>
          )}
        </Stack>
      </Stack>
    </AccessibleTitle>
  );
};
