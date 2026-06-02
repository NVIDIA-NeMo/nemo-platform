// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ColumnFilterPanel } from '@nemo/common/src/components/DataView/ColumnFilterPanel';
import { FilterPanel } from '@nemo/common/src/components/DataView/FilterPanel';
import { Root as DataView } from '@nemo/common/src/components/DataView/internal';
import { StudioAppliedFilters } from '@nemo/common/src/components/DataView/StudioAppliedFilters';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useAgentsListAgents } from '@nemo/sdk/generated/agents/api';
import {
  Banner,
  Block,
  Button,
  Card,
  Collapsible,
  Flex,
  Grid,
  PageHeader,
  Stack,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { loadSnapshot } from '@studio/routes/agents/AgentSuggestionsRoute/api';
import { ApplyEvalConfigModal } from '@studio/routes/agents/AgentSuggestionsRoute/components/ApplyEvalConfigModal';
import {
  EmptyState,
  NoAgentsEmptyState,
} from '@studio/routes/agents/AgentSuggestionsRoute/components/EmptyState';
import { SectionHeading } from '@studio/routes/agents/AgentSuggestionsRoute/components/SectionHeading';
import { SeverityStat } from '@studio/routes/agents/AgentSuggestionsRoute/components/SeverityStat';
import { StatColumn } from '@studio/routes/agents/AgentSuggestionsRoute/components/StatColumn';
import { SuggestionTile } from '@studio/routes/agents/AgentSuggestionsRoute/components/SuggestionTile';
import {
  SCOPE_AGENT,
  SCOPE_OPTIONS,
  SCOPE_WORKSPACE,
  SEVERITY_ORDER,
  STALE_SUGGESTION_MS,
  TYPE_OPTIONS,
} from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type {
  EvalConfigChoice,
  OptimizationSuggestion,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { useOptimizerSuggestions } from '@studio/routes/agents/AgentSuggestionsRoute/useOptimizerSuggestions';
import {
  capitalize,
  countSeverities,
  snapshotAgentNames,
  snapshotModelNames,
  suggestionIdentity,
} from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { getAgentsListRoute } from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Filter, Search } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type FC,
} from 'react';
import { useLocation } from 'react-router-dom';

type MultiState = Record<string, true>;
interface SuggestionFilter {
  agent?: MultiState;
  severity?: MultiState;
  type?: MultiState;
  scope?: MultiState;
}

export const AgentOptimizationsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const location = useLocation();
  const {
    suggestions,
    previousSuggestions,
    isSuggestionsLoading,
    suggestionsLoadError,
    refetchSuggestions,
    phase,
    step,
    error,
    run,
    apply,
    getApplyState,
    getEvalState,
  } = useOptimizerSuggestions(workspace);

  const snapshotQuery = useQuery({
    queryKey: ['agent-optimizer', 'snapshot', workspace] as const,
    queryFn: ({ signal }) => loadSnapshot(workspace, signal),
    enabled: !!workspace,
    retry: false,
  });
  const snapshot = snapshotQuery.data ?? null;

  // Workspace agent count drives whether auto-run fires and which empty
  // state we show — running the optimizer against zero agents is pointless.
  const agentsListQuery = useAgentsListAgents(
    workspace,
    { page: 1, page_size: 1 },
    { query: { enabled: !!workspace } }
  );
  const totalAgentsInWorkspace =
    agentsListQuery.data?.pagination?.total_results ?? agentsListQuery.data?.data?.length ?? 0;
  const hasAgentsInWorkspace = totalAgentsInWorkspace > 0;

  const breadcrumbItems = useMemo(
    () => [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: 'Optimizations' },
    ],
    [workspace]
  );
  useBreadcrumbs({ items: breadcrumbItems });

  const isSnapshotStale = useMemo(() => {
    if (!snapshot?.agents) return false;
    const timestamps = Object.values(snapshot.agents)
      .map((a) => Date.parse(a.updatedAt))
      .filter((t) => !Number.isNaN(t));
    if (timestamps.length === 0) return false;
    return Date.now() - Math.max(...timestamps) > STALE_SUGGESTION_MS;
  }, [snapshot]);

  const didAutoRun = useRef(false);
  // Reset the auto-run guard when the workspace changes so the next workspace
  // visited gets its own initial run.
  useEffect(() => {
    didAutoRun.current = false;
  }, [workspace]);
  useEffect(() => {
    if (didAutoRun.current) return;
    if (isSuggestionsLoading || snapshotQuery.isLoading || agentsListQuery.isLoading) return;
    if (!hasAgentsInWorkspace) return;
    const fromNav = (location.state as { autoRun?: boolean } | null)?.autoRun;
    const isEmptyFirstLoad = !suggestionsLoadError && suggestions.length === 0;
    if (fromNav || isEmptyFirstLoad || isSnapshotStale) {
      didAutoRun.current = true;
      void run();
    }
  }, [
    isSuggestionsLoading,
    snapshotQuery.isLoading,
    agentsListQuery.isLoading,
    hasAgentsInWorkspace,
    suggestionsLoadError,
    suggestions.length,
    isSnapshotStale,
    location.state,
    run,
  ]);

  const isRunning = phase === 'running';

  const [showFilters, setShowFilters] = useState(false);
  const [agentSearch, setAgentSearch] = useState('');
  // Suggestion the user just clicked Apply on — drives the eval-config
  // chooser modal. ``null`` keeps the modal closed.
  const [pendingApply, setPendingApply] = useState<OptimizationSuggestion | null>(null);
  const dataViewState = useStudioDataViewState<SuggestionFilter>({});

  const handleApplyClicked = useCallback(
    (suggestion: OptimizationSuggestion) => {
      // Only ``model_optimization`` suggestions actually run an eval — for
      // everything else (guardrails, data_safety, new_model_scan) there's
      // nothing for the user to choose, so apply immediately.
      if (suggestion.type === 'model_optimization' && suggestion.agent) {
        setPendingApply(suggestion);
        return;
      }
      void apply(suggestion);
    },
    [apply]
  );

  const handleEvalConfigChosen = useCallback(
    (choice: EvalConfigChoice) => {
      const target = pendingApply;
      setPendingApply(null);
      if (!target) return;
      void apply(
        target,
        choice.filesetOverride ? { evalConfigOverride: choice.filesetOverride } : undefined
      );
    },
    [apply, pendingApply]
  );

  // Single pass over ``suggestions`` builds the four filter dropdown
  // option sets — replaces four independent ``useMemo``s that each iterated
  // the array.
  const { agentOptions, scopeOptions, severityOptions, typeOptions } = useMemo(() => {
    const agents = new Set<string>();
    const scopes = new Set<string>();
    const severities = new Set<string>();
    const types = new Set<string>();
    for (const s of suggestions) {
      if (s.agent) agents.add(s.agent);
      scopes.add(s.agent ? SCOPE_AGENT : SCOPE_WORKSPACE);
      severities.add(s.severity ?? 'low');
      types.add(s.type);
    }
    return {
      agentOptions: Array.from(agents)
        .sort()
        .map((value) => ({ value, label: value })),
      scopeOptions: SCOPE_OPTIONS.filter((opt) => scopes.has(opt.value)),
      severityOptions: Array.from(severities)
        .sort((a, b) => (SEVERITY_ORDER[a] ?? 99) - (SEVERITY_ORDER[b] ?? 99))
        .map((value) => ({ value, label: capitalize(value) })),
      typeOptions: TYPE_OPTIONS.filter((opt) => types.has(opt.value)),
    };
  }, [suggestions]);

  const makeColumns = useCallback<
    NonNullable<ComponentProps<typeof DataView<OptimizationSuggestion>>['makeColumns']>
  >(
    ({ accessor }) => [
      accessor((s: OptimizationSuggestion) => s.type, {
        id: 'type',
        header: 'Type',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Type',
            options: typeOptions,
          },
        },
      }),
      accessor((s: OptimizationSuggestion) => s.severity ?? 'low', {
        id: 'severity',
        header: 'Priority',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Priority',
            options: severityOptions,
          },
        },
      }),
      accessor((s: OptimizationSuggestion) => (s.agent ? SCOPE_AGENT : SCOPE_WORKSPACE), {
        id: 'scope',
        header: 'Scope',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Scope',
            options: scopeOptions,
          },
        },
      }),
      accessor((s: OptimizationSuggestion) => s.agent ?? '', {
        id: 'agent',
        header: 'Agent',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Agent',
            options: agentOptions,
          },
        },
      }),
    ],
    [typeOptions, severityOptions, scopeOptions, agentOptions]
  );

  const filterState = dataViewState.apiFilter.filter;
  const agentFilter = filterState?.agent;
  const severityFilter = filterState?.severity;
  const typeFilter = filterState?.type;
  const scopeFilter = filterState?.scope;

  const filteredSuggestions = useMemo(() => {
    const agentKeys = agentFilter ? Object.keys(agentFilter) : [];
    const severityKeys = severityFilter ? Object.keys(severityFilter) : [];
    const typeKeys = typeFilter ? Object.keys(typeFilter) : [];
    const scopeKeys = scopeFilter ? Object.keys(scopeFilter) : [];
    return suggestions.filter((s) => {
      if (agentKeys.length > 0) {
        if (!s.agent || !agentFilter?.[s.agent]) return false;
      }
      if (scopeKeys.length > 0) {
        const scope = s.agent ? SCOPE_AGENT : SCOPE_WORKSPACE;
        if (!scopeFilter?.[scope]) return false;
      }
      if (severityKeys.length > 0 && !severityFilter?.[s.severity ?? 'low']) return false;
      if (typeKeys.length > 0 && !typeFilter?.[s.type]) return false;
      return true;
    });
  }, [suggestions, agentFilter, severityFilter, typeFilter, scopeFilter]);

  // Workspace-wide suggestions sit above per-agent groups in the layout.
  const workspaceSuggestions = useMemo(
    () => filteredSuggestions.filter((s) => !s.agent),
    [filteredSuggestions]
  );

  // Group agent-scoped suggestions by agent name. Track all referenced models
  // per agent so multi-model agents match search against any of their models;
  // also expose the first model as a primary label for the accordion trigger.
  const agentGroups = useMemo(() => {
    const groups = new Map<string, { items: OptimizationSuggestion[]; models: Set<string> }>();
    for (const s of filteredSuggestions) {
      if (!s.agent) continue;
      let group = groups.get(s.agent);
      if (!group) {
        group = { items: [], models: new Set() };
        groups.set(s.agent, group);
      }
      group.items.push(s);
      if (s.model) group.models.add(s.model);
    }
    return Array.from(groups.entries())
      .map(([name, value]) => ({
        name,
        items: value.items,
        models: Array.from(value.models),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [filteredSuggestions]);

  const visibleAgentGroups = useMemo(() => {
    const q = agentSearch.trim().toLowerCase();
    if (!q) return agentGroups;
    return agentGroups.filter(
      (g) => g.name.toLowerCase().includes(q) || g.models.some((m) => m.toLowerCase().includes(q))
    );
  }, [agentGroups, agentSearch]);

  const stats = useMemo(() => {
    const snapshotAgents = snapshotAgentNames(snapshot);
    const snapshotModels = snapshotModelNames(snapshot);
    const agentCount = snapshotAgents.length || agentGroups.length;
    const modelCount =
      snapshotModels.length ||
      new Set(suggestions.map((s) => s.model).filter((m): m is string => !!m)).size;
    return { agentCount, modelCount, ...countSeverities(suggestions) };
  }, [snapshot, agentGroups.length, suggestions]);

  const previousStats = useMemo(() => countSeverities(previousSuggestions), [previousSuggestions]);
  const hasPreviousRun = previousSuggestions.length > 0;

  const hasSuggestions = suggestions.length > 0;
  const showStats = stats.agentCount > 0 && (hasSuggestions || snapshot !== null);

  const renderAgentGroup = useCallback(
    (group: { name: string; models: string[]; items: OptimizationSuggestion[] }) => (
      <Collapsible
        key={group.name}
        defaultOpen
        slotTrigger={
          <button
            type="button"
            className="group flex w-full items-center gap-density-sm py-density-sm text-left"
          >
            <ChevronRight
              size={16}
              className="text-secondary transition-transform duration-150 group-data-[state=open]:rotate-90"
            />
            <Text kind="body/bold/md">{group.name}</Text>
            {group.models.length > 0 && (
              <Text kind="body/regular/sm" color="secondary">
                {group.models.join(', ')}
              </Text>
            )}
          </button>
        }
      >
        <Stack gap="density-md" className="pt-density-sm">
          {group.items.map((suggestion) => {
            const applyState = getApplyState(suggestion);
            return (
              <SuggestionTile
                key={suggestionIdentity(suggestion)}
                suggestion={suggestion}
                onApply={handleApplyClicked}
                isApplying={applyState.isApplying}
                isApplied={applyState.isApplied}
                applyError={applyState.error}
                evalState={getEvalState(suggestion)}
              />
            );
          })}
        </Stack>
      </Collapsible>
    ),
    [getApplyState, getEvalState, handleApplyClicked]
  );

  return (
    <AccessibleTitle title={`Agent Optimizations for ${workspace}`}>
      <Stack className="min-h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Optimization Suggestions"
          slotDescription="Analyze your agents for model sizing opportunities, missing guardrails, data safety issues, and new model availability."
          slotActions={
            <Button kind="primary" onClick={() => void run()} disabled={isRunning}>
              {isRunning
                ? 'Running…'
                : phase === 'done' || phase === 'failed'
                  ? 'Re-run'
                  : 'Generate suggestions'}
            </Button>
          }
        />

        {showStats && (
          <Grid cols={{ md: 1, lg: hasPreviousRun ? 3 : 2 }} gap="density-md">
            <Card>
              <Flex gap="density-2xl">
                <StatColumn label="Agents" value={stats.agentCount} />
                <StatColumn label="Models" value={stats.modelCount} />
              </Flex>
            </Card>
            <Card>
              <Stack gap="density-xxs">
                <Text kind="title/xs" color="secondary">
                  Suggestions
                </Text>
                <Flex gap="density-2xl" align="center">
                  <SeverityStat value={stats.high} label="HIGH" />
                  <SeverityStat value={stats.low} label="LOW" />
                </Flex>
              </Stack>
            </Card>
            {hasPreviousRun && (
              <Card>
                <Stack gap="density-xxs">
                  <Text kind="title/xs" color="secondary">
                    Previous run
                  </Text>
                  <Flex gap="density-2xl" align="center">
                    <SeverityStat value={previousStats.high} label="HIGH" />
                    <SeverityStat value={previousStats.low} label="LOW" />
                  </Flex>
                </Stack>
              </Card>
            )}
          </Grid>
        )}

        {isRunning && (
          <Banner kind="inline" status="info">
            {step}
          </Banner>
        )}
        {phase === 'done' && (
          <Banner kind="inline" status="success">
            {step}
          </Banner>
        )}
        {phase === 'failed' && error && (
          <Banner kind="inline" status="error">
            Analysis failed: {error.message}
          </Banner>
        )}

        {isSuggestionsLoading && <Loading description="Loading suggestions…" />}

        {!isSuggestionsLoading && suggestionsLoadError && (
          <ErrorMessage
            header="Failed to load saved suggestions"
            message={
              suggestionsLoadError instanceof Error ? suggestionsLoadError.message : 'Unknown error'
            }
            slotFooter={
              <Button kind="secondary" size="small" onClick={() => void refetchSuggestions()}>
                Retry
              </Button>
            }
          />
        )}

        {!isSuggestionsLoading &&
          !suggestionsLoadError &&
          !agentsListQuery.isLoading &&
          !hasAgentsInWorkspace && <NoAgentsEmptyState workspace={workspace} />}

        {!isSuggestionsLoading &&
          !suggestionsLoadError &&
          hasAgentsInWorkspace &&
          suggestions.length === 0 &&
          phase === 'idle' && <EmptyState />}

        {!isSuggestionsLoading &&
          !suggestionsLoadError &&
          hasAgentsInWorkspace &&
          suggestions.length === 0 &&
          phase === 'done' && (
            <Text kind="body/regular/sm" color="secondary">
              No issues found — your agents look healthy.
            </Text>
          )}

        {hasSuggestions && (
          <DataView
            dataMode="manual"
            state={dataViewState}
            data={filteredSuggestions}
            makeColumns={makeColumns}
            totalCount={filteredSuggestions.length}
            requestStatus="success"
          >
            <Flex className="min-h-0" gap="density-xl">
              <Block className="flex-1 min-w-0">
                <Stack gap="density-2xl">
                  <Stack gap="density-sm">
                    <Flex justify="end">
                      <Button
                        kind="secondary"
                        aria-pressed={showFilters}
                        onClick={() => setShowFilters((p) => !p)}
                        data-testid="open-filters-button"
                      >
                        <Filter width={12} height={12} />
                        Filters
                      </Button>
                    </Flex>
                    <StudioAppliedFilters />
                  </Stack>

                  {workspaceSuggestions.length > 0 && (
                    <Stack gap="density-md">
                      <SectionHeading>Workspace Suggestions</SectionHeading>
                      <Stack gap="density-md">
                        {workspaceSuggestions.map((suggestion) => {
                          const applyState = getApplyState(suggestion);
                          return (
                            <SuggestionTile
                              key={suggestionIdentity(suggestion)}
                              suggestion={suggestion}
                              onApply={handleApplyClicked}
                              isApplying={applyState.isApplying}
                              isApplied={applyState.isApplied}
                              applyError={applyState.error}
                              evalState={getEvalState(suggestion)}
                            />
                          );
                        })}
                      </Stack>
                    </Stack>
                  )}

                  {agentGroups.length > 0 && (
                    <Stack gap="density-md">
                      <SectionHeading>Agent Suggestions</SectionHeading>
                      <Block className="flex-1 min-w-0">
                        <TextInput
                          slotStart={<Search />}
                          value={agentSearch}
                          placeholder="Search by agent or model name…"
                          onChange={(e) => setAgentSearch(e.target.value)}
                        />
                      </Block>
                      {visibleAgentGroups.length === 0 ? (
                        <Text kind="body/regular/sm" color="secondary">
                          No agents match your search.
                        </Text>
                      ) : (
                        <Stack gap="density-xl">{visibleAgentGroups.map(renderAgentGroup)}</Stack>
                      )}
                    </Stack>
                  )}

                  {workspaceSuggestions.length === 0 && agentGroups.length === 0 && (
                    <Text kind="body/regular/sm" color="secondary">
                      No suggestions match the current filters.
                    </Text>
                  )}
                </Stack>
              </Block>
              <FilterPanel showFilters={showFilters}>
                <ColumnFilterPanel />
              </FilterPanel>
            </Flex>
          </DataView>
        )}
      </Stack>
      <ApplyEvalConfigModal
        open={pendingApply !== null}
        onClose={() => setPendingApply(null)}
        workspace={workspace}
        suggestionTitle={pendingApply?.title ?? ''}
        onConfirm={handleEvalConfigChosen}
      />
    </AccessibleTitle>
  );
};
