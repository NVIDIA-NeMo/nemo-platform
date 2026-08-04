// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Button, Flex, Stack, Tabs, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { useCreateGuardrailCheck, useRunGuardrailChecks } from '@studio/api/guardrail-checks/hooks';
import type { GuardrailCheckEntity } from '@studio/api/guardrail-checks/types';
import { GuardrailChecksDataView } from '@studio/components/dataViews/GuardrailChecksDataView';
import { ResultSummary } from '@studio/components/dataViews/GuardrailChecksDataView/ResultSummary';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import {
  GUARDRAIL_CHECKS_DEFAULT_SUB_TAB,
  GuardrailChecksSubTab,
  isGuardrailChecksSubTab,
} from '@studio/routes/guardrails/GuardrailChecksTab/constants';
import { GuardrailTestCard } from '@studio/routes/guardrails/GuardrailChecksTab/GuardrailTestCard';
import { getGuardrailChecksSubTabRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { ListChecks, Plus, Settings } from 'lucide-react';
import type { FC } from 'react';
import { Link, useParams } from 'react-router-dom';

interface GuardrailTestCasesEditorProps {
  workspace: string;
  configId: string;
  checks: GuardrailCheckEntity[];
}

export const GuardrailTestCasesEditor: FC<GuardrailTestCasesEditorProps> = ({
  workspace,
  configId,
  checks,
}) => {
  const toast = useToast();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  // An unknown segment falls back to the default rather than redirecting, so a hand-typed
  // URL still renders something useful.
  const params = useParams();
  const subTabParam = params[ROUTE_PARAMS.guardrailChecksSubTab];
  const subTab = isGuardrailChecksSubTab(subTabParam)
    ? subTabParam
    : GUARDRAIL_CHECKS_DEFAULT_SUB_TAB;

  const runMutation = useRunGuardrailChecks({
    onSuccess: (results) => {
      const errors = results.filter((r): r is { name: string; error: Error } => 'error' in r);
      if (errors.length) {
        toast.error(`${errors.length} test(s) failed to run`);
      } else {
        toast.success(`Ran ${results.length} test(s) successfully`);
      }
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to run tests'));
    },
  });

  const createMutation = useCreateGuardrailCheck({
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to create test'));
    },
  });

  const handleRunAll = () => {
    if (!checks.length) return;
    runMutation.mutate({ workspace, checks });
  };

  const handleAddTest = () => {
    createMutation.mutate({
      workspace,
      input: {
        parent: configId,
        data: {
          messages: [{ role: 'user', content: '' }],
        },
      },
    });
  };

  return (
    <Stack gap="density-xl" className="w-full min-h-0">
      {/* Heading + sub-tab switcher */}
      <Flex align="center" justify="between" gap="density-md">
        <Text kind="label/bold/lg">Guardrail Test Cases</Text>
        <Flex align="center" gap="density-sm">
          <Button kind="tertiary" color="neutral" size="small" disabled aria-label="Settings">
            <Settings size={16} />
          </Button>
          <LoadingButton
            kind="primary"
            height={32}
            loading={runMutation.isPending}
            disabled={!checks.length || runMutation.isPending}
            onClick={handleRunAll}
          >
            <ListChecks size={16} />
            Run {checks.length} {checks.length === 1 ? 'Test' : 'Tests'}
          </LoadingButton>
        </Flex>
      </Flex>

      {/* Sub-tab switcher */}
      <Tabs
        aria-label="Guardrail test views"
        value={subTab}
        items={[
          {
            value: GuardrailChecksSubTab.Tests,
            children: 'Tests',
            href: getGuardrailChecksSubTabRoute(
              workspace,
              guardrailConfigName,
              GuardrailChecksSubTab.Tests
            ),
          },
          {
            value: GuardrailChecksSubTab.Results,
            children: 'Test Results',
            href: getGuardrailChecksSubTabRoute(
              workspace,
              guardrailConfigName,
              GuardrailChecksSubTab.Results
            ),
          },
        ]}
        renderLink={(item) => <Link to={item.href!}>{item.children}</Link>}
      />

      {/* Tests tab */}
      {subTab === GuardrailChecksSubTab.Tests ? (
        <Stack gap="density-lg">
          {checks.map((check, i) => (
            <GuardrailTestCard key={check.id} check={check} index={i} workspace={workspace} />
          ))}
          <LoadingButton
            kind="secondary"
            height={32}
            loading={createMutation.isPending}
            disabled={createMutation.isPending}
            onClick={handleAddTest}
            className="w-fit"
          >
            <Plus size={16} />
            Add Another Test
          </LoadingButton>
        </Stack>
      ) : (
        /* Test Results tab — summary + table over the loaded checks */
        <Stack gap="density-lg" className="w-full min-h-0">
          <ResultSummary checks={checks} />
          <GuardrailChecksDataView checks={checks} />
        </Stack>
      )}
    </Stack>
  );
};
