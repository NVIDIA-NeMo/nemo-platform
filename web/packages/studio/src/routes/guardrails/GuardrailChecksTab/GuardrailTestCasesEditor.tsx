// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getErrorMessage } from '@nemo/common/src/api/common/utils';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Stack, Tabs, Text } from '@nvidia/foundations-react-core';
import { useCreateGuardrailCheck, useRunGuardrailChecks } from '@studio/api/guardrail-checks/hooks';
import type { GuardrailCheckEntity } from '@studio/api/guardrail-checks/types';
import { GuardrailChecksDataView } from '@studio/components/dataViews/GuardrailChecksDataView';
import { ResultSummary } from '@studio/components/dataViews/GuardrailChecksDataView/ResultSummary';
import { GuardrailCheckDetailSidePanel } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { GuardrailChecksSubTab } from '@studio/routes/guardrails/GuardrailChecksTab/constants';
import { GuardrailTestCard } from '@studio/routes/guardrails/GuardrailChecksTab/GuardrailTestCard';
import { getGuardrailChecksSubTabRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { ListChecks, Plus, Settings } from 'lucide-react';
import { type FC, useCallback, useRef, useState } from 'react';
import { Link } from 'react-router';

interface GuardrailTestCasesEditorProps {
  readonly workspace: string;
  readonly configId: string;
  /** The config's rails, used by the result panel to list guardrail coverage. */
  readonly configData: RailsConfig | undefined;
  readonly checks: GuardrailCheckEntity[];
  /** Which sub-tab to show. The route owns this; an unknown segment redirects upstream. */
  readonly subTab: GuardrailChecksSubTab;
}

export const GuardrailTestCasesEditor: FC<GuardrailTestCasesEditorProps> = ({
  workspace,
  configId,
  configData,
  checks,
  subTab,
}) => {
  const toast = useToast();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  // Per-card flushers, keyed by check name; see `handleRunAll`.
  const flushersRef = useRef(new Map<string, () => Promise<GuardrailCheckEntity>>());
  const [isFlushing, setIsFlushing] = useState(false);

  const runMutation = useRunGuardrailChecks({
    onSuccess: (results) => {
      const errors = results.filter((r): r is { name: string; error: Error } => 'error' in r);
      const [firstError] = errors;
      if (firstError) {
        // The batch swallows per-check failures, so a bare count makes every cause look alike.
        toast.error(
          `${errors.length} test(s) failed to run: ${getErrorMessage(firstError.error, 'Unknown error')}`
        );
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

  const registerFlush = useCallback(
    (name: string, flush: (() => Promise<GuardrailCheckEntity>) | null) => {
      if (flush) flushersRef.current.set(name, flush);
      else flushersRef.current.delete(name);
    },
    []
  );

  const isRunning = isFlushing || runMutation.isPending;

  const handleRunAll = async () => {
    if (!checks.length || isRunning) return;
    setIsFlushing(true);
    try {
      // Clicking Run blurs the focused message, dispatching that card's save. Await it, or the
      // run sends stale text and its write-back 409s against the version that save just bumped.
      const fresh = await Promise.all(
        checks.map((check) => flushersRef.current.get(check.name)?.() ?? Promise.resolve(check))
      );
      runMutation.mutate({ workspace, checks: fresh });
    } finally {
      setIsFlushing(false);
    }
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
            loading={isRunning}
            disabled={!checks.length || isRunning}
            onClick={() => void handleRunAll()}
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
            <GuardrailTestCard
              key={check.id}
              check={check}
              index={i}
              workspace={workspace}
              registerFlush={registerFlush}
            />
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
          <GuardrailChecksDataView
            checks={checks}
            renderDetail={(detail) => (
              <GuardrailCheckDetailSidePanel
                open={detail.open}
                onClose={detail.onClose}
                check={detail.check}
                configData={configData}
                checkIndex={detail.checkIndex}
                visibleIndex={detail.visibleIndex}
                visibleCount={detail.visibleCount}
                onNavigate={detail.onNavigate}
              />
            )}
          />
        </Stack>
      )}
    </Stack>
  );
};
