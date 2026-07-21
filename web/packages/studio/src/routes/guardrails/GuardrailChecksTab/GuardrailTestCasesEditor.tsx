// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  Button,
  Flex,
  Stack,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { useCreateGuardrailCheck, useRunGuardrailChecks } from '@studio/api/guardrail-checks/hooks';
import type { GuardrailCheckEntity } from '@studio/api/guardrail-checks/types';
import { GuardrailChecksDataView } from '@studio/components/dataViews/GuardrailChecksDataView';
import { GuardrailTestCard } from '@studio/routes/guardrails/GuardrailChecksTab/GuardrailTestCard';
import { ListChecks, Plus, Settings } from 'lucide-react';
import { type FC, useState } from 'react';

type SubTab = 'tests' | 'results';

interface GuardrailTestCasesEditorProps {
  workspace: string;
  configId: string;
  configName: string;
  checks: GuardrailCheckEntity[];
}

export const GuardrailTestCasesEditor: FC<GuardrailTestCasesEditorProps> = ({
  workspace,
  configId,
  configName,
  checks,
}) => {
  const toast = useToast();
  const [subTab, setSubTab] = useState<SubTab>('tests');

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
      <TabsRoot value={subTab} onValueChange={(v) => setSubTab(v as SubTab)}>
        <TabsList>
          <TabsTrigger value="tests">Tests</TabsTrigger>
          <TabsTrigger value="results">Test Results</TabsTrigger>
        </TabsList>
      </TabsRoot>

      {/* Tests tab */}
      {subTab === 'tests' ? (
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
        /* Test Results tab — reuse the existing data-view table */
        <GuardrailChecksDataView
          workspace={workspace}
          configId={configId}
          configName={configName}
        />
      )}
    </Stack>
  );
};
