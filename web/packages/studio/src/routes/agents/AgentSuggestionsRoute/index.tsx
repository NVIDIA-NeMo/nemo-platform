// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ColumnFilterPanel } from '@nemo/common/src/components/DataView/ColumnFilterPanel';
import { FilterPanel } from '@nemo/common/src/components/DataView/FilterPanel';
import { Root as DataView } from '@nemo/common/src/components/DataView/internal';
import { StudioAppliedFilters } from '@nemo/common/src/components/DataView/StudioAppliedFilters';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import {
  Banner,
  Block,
  Button,
  Flex,
  PageHeader,
  Stack,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { AgentGroupSection } from '@studio/routes/agents/AgentSuggestionsRoute/components/AgentGroupSection';
import { ApplyEvalConfigModal } from '@studio/routes/agents/AgentSuggestionsRoute/components/ApplyEvalConfigModal';
import {
  EmptyState,
  NoAgentsEmptyState,
} from '@studio/routes/agents/AgentSuggestionsRoute/components/EmptyState';
import { SectionHeading } from '@studio/routes/agents/AgentSuggestionsRoute/components/SectionHeading';
import { StatsSection } from '@studio/routes/agents/AgentSuggestionsRoute/components/StatsSection';
import { SuggestionTile } from '@studio/routes/agents/AgentSuggestionsRoute/components/SuggestionTile';
import { useAgentOptimizations } from '@studio/routes/agents/AgentSuggestionsRoute/useAgentOptimizations';
import { suggestionIdentity } from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { Filter, Search } from 'lucide-react';
import { type FC } from 'react';

export const AgentOptimizationsRoute: FC = () => {
  const {
    workspace,
    isSuggestionsLoading,
    suggestionsLoadError,
    refetchSuggestions,
    phase,
    step,
    error,
    run,
    getApplyState,
    getEvalState,
    agentsListQuery,
    hasAgentsInWorkspace,
    isRunning,
    showFilters,
    setShowFilters,
    agentSearch,
    setAgentSearch,
    pendingApply,
    setPendingApply,
    dataViewState,
    handleApplyClicked,
    handleEvalConfigChosen,
    makeColumns,
    filteredSuggestions,
    workspaceSuggestions,
    agentGroups,
    visibleAgentGroups,
    stats,
    previousStats,
    hasPreviousRun,
    hasSuggestions,
    showStats,
    suggestions,
  } = useAgentOptimizations();

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
          <StatsSection
            stats={stats}
            previousStats={previousStats}
            hasPreviousRun={hasPreviousRun}
          />
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
                        <Stack gap="density-xl">
                          {visibleAgentGroups.map((group) => (
                            <AgentGroupSection
                              key={group.name}
                              group={group}
                              getApplyState={getApplyState}
                              getEvalState={getEvalState}
                              onApply={handleApplyClicked}
                            />
                          ))}
                        </Stack>
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
