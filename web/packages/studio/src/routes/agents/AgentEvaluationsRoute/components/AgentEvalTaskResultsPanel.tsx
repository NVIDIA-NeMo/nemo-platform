// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccordionPanel } from '@nemo/common/src/components/AccordionPanel';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { Badge, Block, Card, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { AgentEvalTaskDetail } from '@studio/api/evaluation/agent-evaluations';
import { formatScore, scoreColor } from '@studio/routes/agents/AgentEvaluationsRoute/evalScores';
import { ListChecks } from 'lucide-react';
import { type FC } from 'react';

interface AgentEvalTaskResultsPanelProps {
  tasks: AgentEvalTaskDetail[];
}

/** Human-readable heading for a task: the email subject (parsed from the
 *  composed instruction's `Subject:` line), falling back to the task id. */
const headingFor = (task: AgentEvalTaskDetail): string => {
  const firstLine = (task.instruction ?? '').split('\n', 1)[0] ?? '';
  const match = /^\s*subject:\s*(.+)$/i.exec(firstLine);
  return match ? match[1].trim() : task.taskId;
};

const referenceText = (reference?: Record<string, unknown>): string | null => {
  if (!reference || Object.keys(reference).length === 0) return null;
  const values = Object.values(reference);
  if (values.length === 1 && typeof values[0] === 'string') return values[0];
  return JSON.stringify(reference);
};

const metadataEntries = (metadata?: Record<string, unknown>): Array<[string, string]> =>
  Object.entries(metadata ?? {}).map(([k, v]) => [
    k,
    typeof v === 'string' ? v : JSON.stringify(v),
  ]);

/** Per-task results, one card each: the agent's response, its metric score(s),
 *  the expected label, the composed input, and provenance metadata. Rebuilt
 *  from the result bundle (trials + scores + tasks) — see this route's AGENTS.md. */
export const AgentEvalTaskResultsPanel: FC<AgentEvalTaskResultsPanelProps> = ({ tasks }) => {
  if (tasks.length === 0) {
    return <Block className="text-subtle">No per-task results recorded for this evaluation.</Block>;
  }

  return (
    <AccordionPanel slotHeading={`Task Results (${tasks.length})`} slotIcon={<ListChecks />}>
      <Stack gap="density-lg">
        {tasks.map((task) => {
          const expected = referenceText(task.reference);
          const metadata = metadataEntries(task.metadata);
          return (
            <Card key={task.taskId} className="relative">
              {/* Score chip pinned top-right so verbose responses read cleanly below it. */}
              <Flex
                gap="density-sm"
                className="absolute right-density-lg top-density-lg"
                wrap="wrap"
              >
                {task.scores.map((s) => (
                  <Badge key={s.name} kind="solid" color={scoreColor(s.value)}>
                    {s.name}: {formatScore(s.value)}
                  </Badge>
                ))}
              </Flex>

              <Stack gap="density-md" className="pr-density-3xl">
                <Stack gap="density-xs">
                  <Text kind="body/semibold/md" className="min-w-0 break-words">
                    {headingFor(task)}
                  </Text>
                  <Flex gap="density-sm" align="center" wrap="wrap">
                    {expected && (
                      <Badge kind="outline" color="gray">
                        Expected: {expected}
                      </Badge>
                    )}
                    <StatusBadge status={task.status} />
                  </Flex>
                </Stack>

                <Stack gap="density-xs">
                  <Text kind="label/bold/sm" color="secondary">
                    Agent response
                  </Text>
                  <Text kind="body/regular/sm" className="whitespace-pre-wrap">
                    {task.responseText ?? '—'}
                  </Text>
                </Stack>

                {task.instruction && (
                  <Stack gap="density-xs">
                    <Text kind="label/bold/sm" color="secondary">
                      Input
                    </Text>
                    <Text kind="body/regular/sm" color="secondary" className="whitespace-pre-wrap">
                      {task.instruction}
                    </Text>
                  </Stack>
                )}

                {metadata.length > 0 && (
                  <Stack gap="density-xs">
                    <Text kind="label/bold/sm" color="secondary">
                      Metadata
                    </Text>
                    <Stack gap="density-xs">
                      {metadata.map(([key, value]) => (
                        <Flex key={key} gap="density-sm" wrap="wrap">
                          <Text kind="body/semibold/sm" color="secondary">
                            {key}:
                          </Text>
                          <Text kind="body/regular/sm" color="secondary" className="break-words">
                            {value}
                          </Text>
                        </Flex>
                      ))}
                    </Stack>
                  </Stack>
                )}

                {task.diagnostics.length > 0 && (
                  <Stack gap="density-xs">
                    <Text kind="label/bold/sm" color="secondary">
                      Diagnostics
                    </Text>
                    <Text kind="body/regular/sm" color="danger" className="whitespace-pre-wrap">
                      {task.diagnostics.map((d) => JSON.stringify(d)).join('\n')}
                    </Text>
                  </Stack>
                )}
              </Stack>
            </Card>
          );
        })}
      </Stack>
    </AccordionPanel>
  );
};
