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
import { type FC, useState } from 'react';
import { useNavigate } from 'react-router';

/** The governed empty-state variants. Errors are handled separately by `ErrorPanel`. */
export type EntityEmptyStateVariant = 'first-use' | 'no-results';

export interface EntityEmptyStateBaseProps {
  entity: EntityKey;
  className?: string;
}

export type EntityEmptyStateProps = EntityEmptyStateBaseProps &
  (
    | {
        variant: 'first-use';
        /**
         * Overrides the registry create action's handler (e.g. opens a create modal).
         * When omitted, a `createAction.to` route is navigated to instead.
         */
        onCreate?: () => void;
        onClearFilters?: undefined;
      }
    | {
        variant: 'no-results';
        /** Clears the active filters/search. Required so `no-results` always offers a way out. */
        onClearFilters: () => void;
        onCreate?: undefined;
      }
  );

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
        <div className="mt-4 w-full max-w-[40rem]">
          <SelfServiceHelp cliCommand={cliCommand} skillPrompt={skillPrompt} />
        </div>
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
 * A compact "Ask an agent · CLI" disclosure: a KUI CodeSnippet (with its
 * built-in copy affordance) whose action row hosts a tiny SegmentedControl to
 * switch between the agent prompt and the CLI command. Kept out of the
 * StatusMessage footer so the ≤2-action rule for empty states holds.
 */
const SelfServiceHelp: FC<{ cliCommand?: string; skillPrompt?: string }> = ({
  cliCommand,
  skillPrompt,
}) => {
  const toast = useToast();
  const [kind, setKind] = useState<HelpKind>(skillPrompt ? 'agent' : 'cli');

  const items: { value: HelpKind; children: React.ReactNode }[] = [];
  if (skillPrompt)
    items.push({
      value: 'agent',
      children: 'Ask an agent',
    });
  if (cliCommand) items.push({ value: 'cli', children: 'CLI' });

  const showCli = kind === 'cli' && !!cliCommand;
  const value = showCli ? (cliCommand as string) : (skillPrompt ?? cliCommand ?? '');
  const language: CodeSnippetLanguage = showCli ? 'bash' : 'markdown';

  return (
    <div className="mt-density-lg" data-testid="entity-empty-state-help">
      <CodeSnippet
        value={value}
        language={language}
        kind="block"
        onCopySuccess={() => toast.success('Copied to clipboard')}
        slotActions={
          items.length > 1 ? (
            <Flex className="w-full" justify="between" align="center" wrap="wrap">
              <SegmentedControl
                size="tiny"
                className="!w-fit"
                value={kind}
                onValueChange={(next) => setKind(next as HelpKind)}
                items={items}
              />
            </Flex>
          ) : undefined
        }
      />
    </div>
  );
};
