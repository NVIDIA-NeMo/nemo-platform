// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { snakeCaseToTitleCase } from '@nemo/common/src/utils/formatters';
import type { EvaluationResponse } from '@nemo/sdk/generated/platform/schema';
import {
  Anchor,
  Button,
  Card,
  Divider,
  Flex,
  PageHeader,
  Stack,
  Table,
  Tag,
  Text,
} from '@nvidia/foundations-react-core';
import {
  getOptimizerGetInsightQueryKey,
  getOptimizerListInsightsQueryKey,
  useOptimizerGetInsight,
  useOptimizerUpdateInsight,
  type InsightStatus,
} from '@studio/api/optimizer';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ChangesetBadge } from '@studio/components/ChangesetBadge';
import {
  deriveEvaluatorNames,
  formatEvaluatorScore,
} from '@studio/components/dataViews/ExperimentGroupDataView/util';
import { ExpandableText } from '@studio/components/ExpandableText';
import { FeatureFlagBadge } from '@studio/components/FeatureFlagBadge';
import { Loading } from '@studio/components/Layouts/Loading';
import { LINK_DOCS_STUDIO_EVALUATION } from '@studio/constants/links';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { InsightOpenModal } from '@studio/routes/optimizer/InsightOpenModal';
import { insightActions, insightStatusColor } from '@studio/routes/optimizer/insightStatus';
import { InsightTracesTable } from '@studio/routes/optimizer/InsightTracesTable';
import { useInsightEvaluations } from '@studio/routes/optimizer/OptimizerInsightRoute/useInsightEvaluations';
import {
  getEvaluationDetailRoute,
  getExperimentGroupDetailRoute,
  getExperimentRoute,
  getOptimizerRoute,
} from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { FlaskConical } from 'lucide-react';
import { type FC, type ReactNode, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

/** A column in the insight page's evaluations table: a header plus a per-evaluation cell renderer. */
interface EvaluationColumn {
  header: string;
  cell: (evaluation: EvaluationResponse) => ReactNode;
  /** Applied to the header cell and every data cell — e.g. to hug + center a column. */
  className?: string;
}

/**
 * Resolves a group's `default_sort` (e.g. `-latency_ms.mean`, `-created_at`,
 * `-evaluators.<name>.mean`) to the table column it sorts by. Returns null for `name` (already the
 * first column) or an unrecognized field.
 */
const resolveSortColumn = (defaultSort: string | undefined): EvaluationColumn | null => {
  const field = (defaultSort ?? '').replace(/^-/, '');
  if (!field || field === 'name') return null;
  if (field === 'created_at')
    return {
      header: 'Created',
      cell: (e) => (e.created_at ? <RelativeTime datetime={e.created_at} /> : '—'),
    };
  if (field === 'run_count') return { header: 'Run Count', cell: (e) => String(e.run_count ?? 0) };
  if (field.startsWith('cost_usd'))
    return {
      header: 'Avg Cost',
      cell: (e) => (e.cost_usd?.mean != null ? `$${e.cost_usd.mean.toFixed(3)}` : '—'),
    };
  if (field.startsWith('latency_ms'))
    return {
      header: 'Avg Latency',
      cell: (e) => (e.latency_ms?.mean != null ? `${Math.round(e.latency_ms.mean)} ms` : '—'),
    };
  const evaluatorMatch = field.match(/^evaluators\.(.+)\.[^.]+$/);
  if (evaluatorMatch) {
    const name = evaluatorMatch[1];
    return {
      header: snakeCaseToTitleCase(name),
      cell: (e) => formatEvaluatorScore(e.aggregate_scores?.[name]?.mean),
    };
  }
  return null;
};

/** The name of the evaluator a group sorts by, if `default_sort` targets an evaluator. */
const sortEvaluatorName = (defaultSort: string | undefined): string | undefined =>
  (defaultSort ?? '').replace(/^-/, '').match(/^evaluators\.(.+)\.[^.]+$/)?.[1];

export const OptimizerInsightRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const { insightId = '' } = useParams<{ insightId: string }>();
  const queryClient = useQueryClient();

  const {
    data: insight,
    isLoading,
    isError,
    refetch,
  } = useOptimizerGetInsight(workspace, insightId);

  const { mutate: updateInsight, isPending: isUpdating } = useOptimizerUpdateInsight({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getOptimizerGetInsightQueryKey(workspace, insightId),
        });
        queryClient.invalidateQueries({
          queryKey: getOptimizerListInsightsQueryKey(workspace),
        });
      },
    },
  });

  const [openModalOpen, setOpenModalOpen] = useState(false);

  const {
    group: experimentGroup,
    evaluations,
    isLoading: evaluationsLoading,
  } = useInsightEvaluations(workspace, insightId);

  // Evaluations table columns: Name, Source, the group's sort-by column, then the first 3
  // evaluators (excluding the sort-by evaluator so it isn't shown twice). Evaluator names come from
  // the shared, alphabetically-sorted deriveEvaluatorNames helper so this table's column order is
  // stable across loads and consistent with the experiment group page. (No column filters here.)
  const sortByColumn = resolveSortColumn(experimentGroup?.default_sort);
  const sortEvaluator = sortEvaluatorName(experimentGroup?.default_sort);
  const evaluatorColumns = deriveEvaluatorNames(evaluations, [])
    .filter((name) => name !== sortEvaluator)
    .slice(0, 3);
  const evaluationColumns: EvaluationColumn[] = [
    // Name is the only greedy column (w-full) — it absorbs the space the hugging columns don't use.
    { header: 'Name', className: 'w-full', cell: (e) => e.name },
    {
      header: 'Source',
      className: 'text-center',
      cell: (e) => (e.source_link ? <ChangesetBadge href={e.source_link} /> : null),
    },
    ...(sortByColumn ? [sortByColumn] : []),
    ...evaluatorColumns.map((name) => ({
      header: snakeCaseToTitleCase(name),
      cell: (e: EvaluationResponse) => formatEvaluatorScore(e.aggregate_scores?.[name]?.mean),
    })),
  ];

  const changeStatus = (status: InsightStatus) =>
    updateInsight({ workspace, insightId, data: { status } });

  // The "open" action only shows the modal with the CLI command to run experiments — it does not
  // change the insight's status. The external agent transitions the insight to `open` when it
  // actually creates experiments for it. Every other action applies its status change directly.
  const handleAction = (target: InsightStatus) => {
    if (target === 'open') {
      setOpenModalOpen(true);
    } else {
      changeStatus(target);
    }
  };

  useBreadcrumbs({
    items: [
      { href: getOptimizerRoute(workspace), slotLabel: 'Insights' },
      { slotLabel: insight?.title ?? insightId },
    ],
  });

  if (isLoading && !insight) {
    return <Loading description="Loading insight..." />;
  }

  if (isError || !insight) {
    return (
      <AccessibleTitle title="Insight">
        <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
          <ErrorMessage
            header="Failed to load insight"
            message="The insight could not be loaded. It may have been deleted or you may not have access."
            slotFooter={
              <Flex gap="density-sm">
                <Button type="button" kind="tertiary" onClick={() => refetch()}>
                  Retry
                </Button>
                <Link to={getOptimizerRoute(workspace)}>
                  <Button kind="secondary">Back to Optimizer</Button>
                </Link>
              </Flex>
            }
          />
        </Stack>
      </AccessibleTitle>
    );
  }

  const traceRefs = insight.trace_refs ?? [];

  return (
    <AccessibleTitle title={`Insight - ${insight.title}`}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading={
            <Flex className="items-center gap-density-md">
              {insight.title}
              <FeatureFlagBadge flag="optimizerEnabled" />
            </Flex>
          }
          slotDescription={
            <>
              Insight generated from observed sessions by the analyst agent.{' '}
              <Anchor href={LINK_DOCS_STUDIO_EVALUATION} target="_blank">
                Learn more
              </Anchor>
            </>
          }
          slotActions={
            <Flex gap="density-sm">
              {insightActions(insight.status).map((action) => (
                <Button
                  key={action.target}
                  kind={action.kind}
                  color={action.color}
                  disabled={isUpdating}
                  onClick={() => handleAction(action.target)}
                >
                  {action.label}
                </Button>
              ))}
            </Flex>
          }
        />

        <div className="flex gap-8">
          <KVPair
            label="Status"
            orientation="vertical"
            value={
              <Tag kind="outline" color={insightStatusColor(insight.status)} readOnly>
                {insight.status}
              </Tag>
            }
          />
          <Divider orientation="vertical" className="grow-0 self-stretch" />
          <KVPair label="Agent" orientation="vertical" value={insight.agent || '—'} />
          <Divider orientation="vertical" className="grow-0 self-stretch" />
          <KVPair
            label="Created"
            orientation="vertical"
            value={insight.created_at ? <RelativeTime datetime={insight.created_at} /> : '—'}
          />
          <Divider orientation="vertical" className="grow-0 self-stretch" />
          <KVPair
            label="Updated"
            orientation="vertical"
            value={insight.updated_at ? <RelativeTime datetime={insight.updated_at} /> : '—'}
          />
        </div>

        <div className="flex items-stretch gap-density-lg">
          <Card className="w-1/2">
            <Stack className="h-full gap-density-sm">
              <Text kind="label/bold/md">Description</Text>
              {insight.description ? (
                <ExpandableText text={insight.description} fill />
              ) : (
                <Text kind="body/regular/md">—</Text>
              )}
            </Stack>
          </Card>

          <Card className="w-1/2 min-w-0">
            <Stack className="min-w-0 gap-density-md">
              <Text kind="label/bold/md">Evaluations</Text>
              {evaluations.length > 0 ? (
                <div className="overflow-x-auto">
                  <Table
                    className="w-full bg-transparent [&_.nv-table-row]:border-b-0"
                    align="left"
                    layout="auto"
                    hoverableRows
                    columns={evaluationColumns.map((column) => ({
                      children: column.header,
                      // Every column hugs its content (nowrap); only Name (w-full) takes the rest.
                      attributes: {
                        TableHeaderCell: {
                          className: `whitespace-nowrap ${column.className ?? ''}`,
                        },
                      },
                    }))}
                    rows={evaluations.map((evaluation) => ({
                      id: evaluation.name,
                      onRowSelect: () =>
                        navigate(
                          getEvaluationDetailRoute(
                            workspace,
                            experimentGroup?.name ?? '',
                            evaluation.name
                          )
                        ),
                      cells: evaluationColumns.map((column) => ({
                        children: column.cell(evaluation),
                        attributes: {
                          TableDataCell: {
                            className: `whitespace-nowrap ${column.className ?? ''}`,
                          },
                        },
                      })),
                    }))}
                  />
                </div>
              ) : evaluationsLoading ? (
                <Text kind="body/regular/md" className="text-secondary">
                  Loading evaluations…
                </Text>
              ) : (
                <Stack className="items-center gap-density-md py-density-2xl">
                  <FlaskConical className="size-12 text-secondary" />
                  <Text kind="body/regular/md" className="text-secondary">
                    No evaluations for this insight
                  </Text>
                  <Button
                    kind="primary"
                    color="brand"
                    disabled={isUpdating}
                    onClick={() => handleAction('open')}
                  >
                    Run experiment
                  </Button>
                </Stack>
              )}
              {evaluations.length > 0 ? (
                <>
                  <Divider className="grow-0" />
                  <Flex justify="end">
                    <Button asChild kind="tertiary">
                      <Link
                        to={
                          experimentGroup
                            ? getExperimentGroupDetailRoute(workspace, experimentGroup.name)
                            : getExperimentRoute(workspace)
                        }
                      >
                        View {experimentGroup?.evaluation_count ?? evaluations.length} Evaluations
                      </Link>
                    </Button>
                  </Flex>
                </>
              ) : null}
            </Stack>
          </Card>
        </div>

        <Stack className="gap-density-sm">
          <Text kind="label/bold/md">Observed Sessions ({traceRefs.length})</Text>
          <InsightTracesTable workspace={workspace} traceIds={traceRefs} />
        </Stack>
      </Stack>

      <InsightOpenModal
        open={openModalOpen}
        insight={insight}
        onClose={() => setOpenModalOpen(false)}
      />
    </AccessibleTitle>
  );
};
