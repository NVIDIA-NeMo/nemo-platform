// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ENTITY_EMPTY_STATES,
  type EntityKey,
} from '@nemo/common/src/components/EntityEmptyState/registry';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  Button,
  CodeSnippet,
  type CodeSnippetLanguage,
  Flex,
  SegmentedControl,
  StatusMessage,
} from '@nvidia/foundations-react-core';
import { TriangleAlert } from 'lucide-react';
import { type FC, useState } from 'react';
import { useNavigate } from 'react-router';

/** The three governed empty-state variants. */
export type EntityEmptyStateVariant = 'first-use' | 'no-results' | 'error';

export interface EntityEmptyStateProps {
  entity: EntityKey;
  variant: EntityEmptyStateVariant;
  /**
   * Overrides the registry create action's handler (e.g. opens a create modal).
   * When omitted, a `createAction.to` route is navigated to instead.
   * `first-use` only.
   */
  onCreate?: () => void;
  /** Clears the active filters/search. `no-results` only. */
  onClearFilters?: () => void;
  /** Re-runs the failed request. `error` only. */
  onRetry?: () => void;
  className?: string;
}

/**
 * The single canonical empty state for Studio lists, tables, and panels. Copy,
 * iconography, CLI command, and skill prompt come from the entity registry; the
 * variant selects which affordances render. See the `ui-design` skill's
 * `empty-states` reference.
 */
export const EntityEmptyState: FC<EntityEmptyStateProps> = ({
  entity,
  variant,
  onCreate,
  onClearFilters,
  onRetry,
  className,
}) => {
  const descriptor = ENTITY_EMPTY_STATES[entity];
  const navigate = useNavigate();

  if (variant === 'no-results') {
    return (
      <Centered className={className} testId="entity-empty-state-no-results">
        <StatusMessage
          slotHeading="No results found"
          slotSubheading="No items match your current search or filters."
          slotFooter={
            onClearFilters ? (
              <Button kind="tertiary" onClick={onClearFilters}>
                Clear filters
              </Button>
            ) : null
          }
        />
      </Centered>
    );
  }

  if (variant === 'error') {
    return (
      <Centered className={className} testId="entity-empty-state-error">
        <StatusMessage
          slotMedia={<TriangleAlert className="size-12 text-feedback-danger" />}
          slotHeading="Something went wrong"
          slotSubheading="We couldn't load this list. Please try again."
          slotFooter={
            onRetry ? (
              <Button color="brand" onClick={onRetry}>
                Try again
              </Button>
            ) : null
          }
        />
      </Centered>
    );
  }

  const { icon: Icon, heading, subheading, createAction, cliCommand, skillPrompt } = descriptor;
  const handleCreate =
    onCreate ?? (createAction?.to ? () => navigate(createAction.to as string) : undefined);

  return (
    <Centered className={className} testId="entity-empty-state-first-use">
      <StatusMessage
        slotMedia={<Icon className="size-12" />}
        slotHeading={heading}
        slotSubheading={subheading}
        slotFooter={
          createAction && handleCreate ? (
            <Button color="brand" onClick={handleCreate}>
              {createAction.label}
            </Button>
          ) : null
        }
      />
      {(cliCommand || skillPrompt) && (
        <SelfServiceHelp cliCommand={cliCommand} skillPrompt={skillPrompt} />
      )}
    </Centered>
  );
};

const Centered: FC<{ children: React.ReactNode; className?: string; testId: string }> = ({
  children,
  className,
  testId,
}) => (
  <Flex
    direction="col"
    align="center"
    justify="center"
    className={`h-full w-full ${className ?? ''}`}
    data-testid={testId}
  >
    {children}
  </Flex>
);

/** Self-service help kind. */
type HelpKind = 'cli' | 'agent';

/**
 * A compact "NeMo CLI · Ask an Agent" disclosure: a KUI CodeSnippet (with its
 * built-in copy affordance) whose action row hosts a tiny SegmentedControl to
 * switch between the CLI command and the agent prompt. Kept out of the
 * StatusMessage footer so the ≤2-action rule for empty states holds.
 */
const SelfServiceHelp: FC<{ cliCommand?: string; skillPrompt?: string }> = ({
  cliCommand,
  skillPrompt,
}) => {
  const toast = useToast();
  const [kind, setKind] = useState<HelpKind>(cliCommand ? 'cli' : 'agent');

  const items: { value: HelpKind; children: string }[] = [];
  if (cliCommand) items.push({ value: 'cli', children: 'NeMo CLI' });
  if (skillPrompt) items.push({ value: 'agent', children: 'Ask an Agent' });

  const showCli = kind === 'cli' && !!cliCommand;
  const value = showCli ? (cliCommand as string) : (skillPrompt ?? cliCommand ?? '');
  const language: CodeSnippetLanguage = showCli ? 'bash' : 'markdown';

  return (
    <div className="mt-density-lg w-full max-w-[32rem]" data-testid="entity-empty-state-help">
      <CodeSnippet
        value={value}
        language={language}
        kind="block"
        onCopySuccess={() => toast.success('Copied to clipboard')}
        slotActions={
          items.length > 1 ? (
            <SegmentedControl
              size="small"
              value={kind}
              onValueChange={(next) => setKind(next as HelpKind)}
              items={items}
            />
          ) : undefined
        }
      />
    </div>
  );
};
