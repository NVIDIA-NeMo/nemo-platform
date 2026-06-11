// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import {
  Button,
  CodeSnippet,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { LINK_DOCS_EXPERIMENTS_CLI } from '@studio/constants/links';
import { Bot, ChevronRight, File, FlaskConical, Terminal } from 'lucide-react';

interface EmptyProps {
  experimentGroupName: string;
  datasetName: string;
}

export const Empty = ({ experimentGroupName, datasetName }: EmptyProps) => {
  const cliCommand =
    `nemo exp run \\\n` +
    `  --group "${experimentGroupName}" \\\n` +
    `  --dataset "${datasetName}" \\\n` +
    `  --evaluators correctness,helpfulness,groundedness,tool-error`;

  return (
    <TableEmptyState
      icon={<FlaskConical className="size-12" />}
      header="No test cases"
      emptyMessage="Run an experiment to see test case results."
      actions={
        <div className="w-[560px] border border-base rounded-lg overflow-hidden">
          <TabsRoot defaultValue="cli">
            <TabsList className="px-density-md">
              <TabsTrigger value="coding-agent">
                <Bot className="size-4" />
                Coding agent
              </TabsTrigger>
              <TabsTrigger value="cli">
                <Terminal className="size-4" />
                CLI command
              </TabsTrigger>
            </TabsList>
            <div className="px-density-md pb-density-md flex flex-col gap-density-sm">
              <TabsContent value="coding-agent" className="px-0 pb-0 w-full">
                <CodeSnippet
                  value="To be determined"
                  language="text"
                  kind="block"
                  className="w-full whitespace-pre-line"
                />
              </TabsContent>
              <TabsContent value="cli" className="px-0 pb-0">
                <CodeSnippet value={cliCommand} language="bash" kind="block" className="w-full" />
              </TabsContent>
              <Button
                asChild
                color="neutral"
                kind="tertiary"
                size="small"
                className="w-full justify-start"
              >
                <a href={LINK_DOCS_EXPERIMENTS_CLI} target="_blank" rel="noreferrer">
                  <File className="!text-brand" />
                  <Text className="flex-1">CLI docs — learn more</Text>
                  <ChevronRight />
                </a>
              </Button>
            </div>
          </TabsRoot>
        </div>
      }
    />
  );
};
