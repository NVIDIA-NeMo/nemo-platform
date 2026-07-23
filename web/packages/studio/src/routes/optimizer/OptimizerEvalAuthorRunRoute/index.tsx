// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useFilesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import {
  Anchor,
  Banner,
  Button,
  Flex,
  Grid,
  PageHeader,
  Panel,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { type EvalAuthorRun, useOptimizerGetEvalAuthorRun } from '@studio/api/optimizer';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { FilesetFilePreviewContent } from '@studio/components/FilesetFilePreviewPanel/FilesetFilePreviewContent';
import { Loading } from '@studio/components/Layouts/Loading';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { EvalAuthorRunStatusBadge } from '@studio/routes/optimizer/EvalAuthorRunStatusBadge';
import {
  ArtifactCode,
  DownloadArtifactButton,
} from '@studio/routes/optimizer/OptimizerEvalAuthorRunRoute/artifacts';
import {
  parseArtifactJson,
  parseFilesetRef,
  useArtifactText,
} from '@studio/routes/optimizer/OptimizerEvalAuthorRunRoute/artifactUtils';
import {
  getFilesetDetailRoute,
  getIntakeTraceRoute,
  getOptimizerInsightRoute,
  getOptimizerRoute,
} from '@studio/routes/utils';
import { useEffect, useMemo, useState, type FC, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';

interface ArtifactManifest {
  schema_version: number;
  prompt_requests?: Array<{ attempt: number; turn: number; path: string }>;
}

interface CapturedRequest {
  schema_version?: number;
  captured_at?: string;
  attempt?: number;
  turn?: number;
  model?: string;
  messages?: Array<{ role?: string; content?: unknown }>;
  params?: Record<string, unknown>;
  redactions?: { applied?: boolean; fields?: string[] };
}

interface VerifierManifest {
  schema_version: number;
  entrypoint?: string;
  metrics?: Array<{
    name: string;
    reward_keys?: string[];
    entrypoint?: string;
    files?: Array<{
      path: string;
      artifact_path?: string;
      language?: string;
      sha256?: string;
      applied_to_train_tasks?: number;
      applied_to_validation_tasks?: number;
    }>;
  }>;
}

const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled']);

const isTerminal = (run: EvalAuthorRun | undefined) => !!run && TERMINAL_STATUSES.has(run.status);

const duration = (run: EvalAuthorRun): string => {
  if (!run.started_at) return '—';
  const end = run.completed_at ? Date.parse(run.completed_at) : Date.now();
  const seconds = Math.max(0, Math.round((end - Date.parse(run.started_at)) / 1_000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
};

const filesetLink = (ref: string | null | undefined): ReactNode => {
  const fileset = parseFilesetRef(ref);
  if (!fileset || !ref) return '—';
  return (
    <Link
      className="text-primary underline"
      to={getFilesetDetailRoute(fileset.workspace, fileset.name)}
    >
      {ref}
    </Link>
  );
};

const OverviewTab: FC<{ run: EvalAuthorRun }> = ({ run }) => (
  <Stack gap="density-xl" className="py-density-lg">
    {run.error && (
      <Banner kind="inline" status="error" title="Run failed">
        {run.error}
      </Banner>
    )}
    <Grid cols={{ base: 1, xl: 2 }} gap="density-xl">
      <Panel slotHeading="Run" elevation="high" density="compact">
        <Stack gap="density-md">
          <KVPair label="Status" value={<EvalAuthorRunStatusBadge status={run.status} />} />
          <KVPair label="Stage" value={run.stage.replaceAll('_', ' ')} />
          <KVPair label="Evaluator" value={run.evaluator_type} />
          <KVPair label="Duration" value={duration(run)} />
          <KVPair
            label="Started"
            value={run.started_at ? <RelativeTime datetime={run.started_at} /> : '—'}
          />
          <KVPair
            label="Completed"
            value={run.completed_at ? <RelativeTime datetime={run.completed_at} /> : '—'}
          />
        </Stack>
      </Panel>
      <Panel slotHeading="Inputs and models" elevation="high" density="compact">
        <Stack gap="density-md">
          <KVPair label="Agent" value={run.inputs.agent} />
          <KVPair label="Production traces" value={String(run.inputs.trace_refs.length)} />
          <KVPair label="Smart model" value={run.models.smart} />
          <KVPair label="Fast model" value={run.models.fast} />
          <KVPair label="Task template" value={run.inputs.task_template} />
          <KVPair label="Train source" value={run.inputs.train_dataset} />
          <KVPair label="Validation source" value={run.inputs.validation_dataset} />
        </Stack>
      </Panel>
      <Panel slotHeading="Result" elevation="high" density="compact">
        <Stack gap="density-md">
          <KVPair label="Metrics" value={run.outputs.metric_names.join(', ') || '—'} />
          <KVPair label="Train tasks" value={String(run.outputs.train_task_count)} />
          <KVPair label="Validation tasks" value={String(run.outputs.validation_task_count)} />
          <KVPair label="Validation" value={run.validation.status} />
          <KVPair label="Validation attempts" value={String(run.validation.attempt_count)} />
          <KVPair label="Summary" value={run.summary || '—'} />
        </Stack>
      </Panel>
      <Panel slotHeading="Provenance" elevation="high" density="compact">
        <Stack gap="density-md">
          <KVPair label="Optimizer branch" value={run.provenance.optimizer_branch} />
          <KVPair label="Optimizer commit" value={run.provenance.optimizer_commit} />
          <KVPair label="Runner" value={run.provenance.runner} />
          <KVPair
            label="Configuration"
            value={
              <CodeEditor
                className="min-h-[160px]"
                content={JSON.stringify(run.config, null, 2)}
                contentType={ContentType.JSON}
                readOnly
              />
            }
          />
        </Stack>
      </Panel>
    </Grid>
    <Panel slotHeading="Output Filesets" elevation="high" density="compact">
      <Grid cols={{ base: 1, xl: 2 }} gap="density-md">
        <KVPair label="Artifacts" value={filesetLink(run.outputs.artifact_fileset)} />
        <KVPair label="Insight suite" value={filesetLink(run.outputs.insight_suite)} />
        <KVPair label="Authored train dataset" value={filesetLink(run.outputs.train_dataset)} />
        <KVPair
          label="Authored validation dataset"
          value={filesetLink(run.outputs.validation_dataset)}
        />
      </Grid>
    </Panel>
  </Stack>
);

const PromptTab: FC<{ run: EvalAuthorRun }> = ({ run }) => {
  const fileset = parseFilesetRef(run.outputs.artifact_fileset);
  const manifestQuery = useArtifactText(fileset, 'manifest.json', !!fileset);
  const manifest = parseArtifactJson<ArtifactManifest>(manifestQuery.data);
  const requests = useMemo(() => manifest?.prompt_requests ?? [], [manifest?.prompt_requests]);
  const [selectedPath, setSelectedPath] = useState<string>('');

  useEffect(() => {
    if (!selectedPath && requests[0]?.path) setSelectedPath(requests[0].path);
  }, [requests, selectedPath]);

  const requestQuery = useArtifactText(fileset, selectedPath, !!selectedPath);
  const request = parseArtifactJson<CapturedRequest>(requestQuery.data);
  const trajectoryQuery = useArtifactText(
    fileset,
    'trajectory/atif.json',
    run.capture.trajectory !== 'unavailable'
  );

  if (run.capture.prompt === 'unavailable') {
    return (
      <Banner className="mt-density-lg" kind="inline" status="info" title="Prompt not captured">
        Not captured for this legacy run. The request cannot be reconstructed after execution.
      </Banner>
    );
  }

  return (
    <Stack gap="density-xl" className="py-density-lg">
      {(run.capture.redactions || request?.redactions?.applied) && (
        <Banner kind="inline" status="warning" title="Captured with redactions">
          The effective request is exact except for named secret redactions:{' '}
          {[...run.capture.redacted_fields, ...(request?.redactions?.fields ?? [])].join(', ') ||
            'sensitive values'}
          .
        </Banner>
      )}
      <Flex align="center" justify="between" gap="density-md">
        <SelectRoot value={selectedPath} onValueChange={(value: string) => setSelectedPath(value)}>
          <SelectTrigger
            placeholder="Select authoring turn"
            renderValue={() => {
              const selected = requests.find((item) => item.path === selectedPath);
              return selected ? `Attempt ${selected.attempt}, turn ${selected.turn}` : null;
            }}
          />
          <SelectContent>
            <SelectListbox>
              {requests.map((item) => (
                <SelectItem key={item.path} value={item.path}>
                  Attempt {item.attempt}, turn {item.turn}
                </SelectItem>
              ))}
            </SelectListbox>
          </SelectContent>
        </SelectRoot>
        {fileset && selectedPath && (
          <DownloadArtifactButton fileset={fileset} path={selectedPath} />
        )}
      </Flex>
      <Grid cols={{ base: 1, xl: 2 }} gap="density-xl">
        <Panel slotHeading="Effective model request" elevation="high" density="compact">
          <Stack gap="density-lg">
            <KVPair label="Model" value={request?.model ?? '—'} />
            <KVPair
              label="Sampling and tools"
              value={
                <CodeEditor
                  className="min-h-[240px]"
                  content={JSON.stringify(request?.params ?? {}, null, 2)}
                  contentType={ContentType.JSON}
                  readOnly
                />
              }
            />
            <Stack gap="density-md">
              {(request?.messages ?? []).map((message, index) => (
                <Panel
                  key={`${message.role ?? 'message'}-${index}`}
                  slotHeading={message.role ?? `Message ${index + 1}`}
                  density="compact"
                >
                  <Text className="whitespace-pre-wrap break-words">
                    {typeof message.content === 'string'
                      ? message.content
                      : JSON.stringify(message.content, null, 2)}
                  </Text>
                </Panel>
              ))}
            </Stack>
          </Stack>
        </Panel>
        <Panel slotHeading="Trajectory" elevation="high" density="compact">
          <ArtifactCode
            content={trajectoryQuery.data}
            loading={trajectoryQuery.isLoading}
            emptyMessage="No trajectory artifact was captured."
          />
        </Panel>
      </Grid>
    </Stack>
  );
};

const VerifierTab: FC<{ run: EvalAuthorRun }> = ({ run }) => {
  const fileset = parseFilesetRef(run.outputs.artifact_fileset);
  const manifestQuery = useArtifactText(fileset, 'verifier/manifest.json', !!fileset);
  const manifest = parseArtifactJson<VerifierManifest>(manifestQuery.data);
  const metrics = useMemo(() => manifest?.metrics ?? [], [manifest?.metrics]);
  const [metricName, setMetricName] = useState('');
  const [filePath, setFilePath] = useState('');
  const metric = metrics.find((item) => item.name === metricName) ?? metrics[0];
  const files = useMemo(() => metric?.files ?? [], [metric?.files]);

  useEffect(() => {
    if (!metricName && metrics[0]?.name) setMetricName(metrics[0].name);
  }, [metricName, metrics]);
  useEffect(() => {
    const next =
      files[0]?.artifact_path ?? (files[0]?.path ? `verifier/files/${files[0].path}` : '');
    if (
      !filePath ||
      !files.some((file) => (file.artifact_path ?? `verifier/files/${file.path}`) === filePath)
    ) {
      setFilePath(next);
    }
  }, [filePath, files]);

  const sourceQuery = useArtifactText(fileset, filePath, !!filePath);
  const selectedFile = files.find(
    (file) => (file.artifact_path ?? `verifier/files/${file.path}`) === filePath
  );

  return (
    <Stack gap="density-xl" className="py-density-lg">
      <Flex gap="density-md" wrap="wrap">
        <SelectRoot
          value={metric?.name ?? ''}
          onValueChange={(value: string) => setMetricName(value)}
        >
          <SelectTrigger placeholder="Select metric" />
          <SelectContent>
            <SelectListbox>
              {metrics.map((item) => (
                <SelectItem key={item.name} value={item.name}>
                  {item.name}
                </SelectItem>
              ))}
            </SelectListbox>
          </SelectContent>
        </SelectRoot>
        <SelectRoot value={filePath} onValueChange={(value: string) => setFilePath(value)}>
          <SelectTrigger placeholder="Select generated file" />
          <SelectContent>
            <SelectListbox>
              {files.map((file) => {
                const path = file.artifact_path ?? `verifier/files/${file.path}`;
                return (
                  <SelectItem key={path} value={path}>
                    {file.path}
                  </SelectItem>
                );
              })}
            </SelectListbox>
          </SelectContent>
        </SelectRoot>
      </Flex>
      <Grid cols={{ base: 1, xl: 3 }} gap="density-xl">
        <Panel slotHeading="Verifier contract" elevation="high" density="compact">
          <Stack gap="density-md">
            <KVPair label="Metric" value={metric?.name ?? '—'} />
            <KVPair label="Entrypoint" value={metric?.entrypoint ?? manifest?.entrypoint ?? '—'} />
            <KVPair label="Reward keys" value={metric?.reward_keys?.join(', ') ?? '—'} />
            <KVPair label="SHA-256" value={selectedFile?.sha256 ?? '—'} />
            <KVPair
              label="Applied to train tasks"
              value={String(selectedFile?.applied_to_train_tasks ?? 0)}
            />
            <KVPair
              label="Applied to validation tasks"
              value={String(selectedFile?.applied_to_validation_tasks ?? 0)}
            />
            <KVPair label="Validation" value={run.validation.status} />
            <KVPair label="Repair attempts" value={String(run.validation.attempt_count)} />
          </Stack>
        </Panel>
        <div className="xl:col-span-2">
          <Panel
            slotHeading={selectedFile?.path ?? 'Generated source'}
            elevation="high"
            density="compact"
          >
            <ArtifactCode
              content={sourceQuery.data}
              loading={sourceQuery.isLoading}
              contentType={
                selectedFile?.language === 'python' ? ContentType.PYTHON : ContentType.TEXT
              }
              emptyMessage="No generated verifier source was captured."
            />
          </Panel>
        </div>
      </Grid>
      <Flex gap="density-md">
        {run.outputs.train_dataset && filesetLink(run.outputs.train_dataset)}
        {run.outputs.validation_dataset && filesetLink(run.outputs.validation_dataset)}
      </Flex>
    </Stack>
  );
};

const DataTab: FC<{ run: EvalAuthorRun }> = ({ run }) => {
  const fileset = parseFilesetRef(run.outputs.artifact_fileset);
  const insightQuery = useArtifactText(fileset, 'analysis/insight.json', !!fileset);
  const conventionsQuery = useArtifactText(fileset, 'analysis/runner-conventions.md', !!fileset);
  const validationQuery = useArtifactText(fileset, 'validation/attempts.json', !!fileset);

  return (
    <Stack gap="density-xl" className="py-density-lg">
      <Panel slotHeading="Production evidence" elevation="high" density="compact">
        <Flex gap="density-md" wrap="wrap">
          {run.inputs.trace_refs.map((traceId) => (
            <Link
              key={traceId}
              className="text-primary underline"
              to={getIntakeTraceRoute(run.workspace, traceId)}
            >
              {traceId}
            </Link>
          ))}
        </Flex>
      </Panel>
      <Grid cols={{ base: 1, xl: 2 }} gap="density-xl">
        <Panel slotHeading="Insight snapshot" elevation="high" density="compact">
          <ArtifactCode
            content={insightQuery.data}
            loading={insightQuery.isLoading}
            emptyMessage="No Insight snapshot was captured."
          />
        </Panel>
        <Panel slotHeading="Runner conventions" elevation="high" density="compact">
          <ArtifactCode
            content={conventionsQuery.data}
            loading={conventionsQuery.isLoading}
            contentType={ContentType.TEXT}
            emptyMessage="No runner conventions were captured."
          />
        </Panel>
        <Panel slotHeading="Validation attempts" elevation="high" density="compact">
          <ArtifactCode
            content={validationQuery.data}
            loading={validationQuery.isLoading}
            emptyMessage="No validation-attempt artifact was captured."
          />
        </Panel>
        <Panel slotHeading="Dataset and source artifacts" elevation="high" density="compact">
          <Stack gap="density-md">
            <KVPair label="Source agent" value="source-agent/" />
            <KVPair label="Task template" value={run.inputs.task_template} />
            <KVPair label="Train input" value={run.inputs.train_dataset} />
            <KVPair label="Validation input" value={run.inputs.validation_dataset} />
            <KVPair label="Train output" value={filesetLink(run.outputs.train_dataset)} />
            <KVPair label="Validation output" value={filesetLink(run.outputs.validation_dataset)} />
            <KVPair label="Insight suite" value={filesetLink(run.outputs.insight_suite)} />
          </Stack>
        </Panel>
      </Grid>
    </Stack>
  );
};

const ArtifactsTab: FC<{ run: EvalAuthorRun }> = ({ run }) => {
  const fileset = parseFilesetRef(run.outputs.artifact_fileset);
  const {
    data: response,
    isLoading,
    isError,
  } = useFilesListFilesetFiles(fileset?.workspace ?? '', fileset?.name ?? '', undefined, {
    query: { enabled: !!fileset },
  });
  const files = useMemo(() => response?.data ?? [], [response?.data]);
  const [selectedPath, setSelectedPath] = useState('');

  if (!fileset) {
    return (
      <Banner className="mt-density-lg" kind="inline" status="info">
        This run has no artifact Fileset.
      </Banner>
    );
  }

  return (
    <Stack gap="density-lg" className="min-h-[600px] py-density-lg">
      <Flex justify="between" align="center">
        <Anchor asChild>
          <Link to={getFilesetDetailRoute(fileset.workspace, fileset.name)}>
            Browse full Fileset
          </Link>
        </Anchor>
        {selectedPath && <DownloadArtifactButton fileset={fileset} path={selectedPath} />}
      </Flex>
      {isError ? (
        <ErrorMessage
          header="Failed to load artifacts"
          message="The artifact Fileset could not be listed."
        />
      ) : (
        <Grid cols={{ base: 1, xl: 3 }} gap="density-lg" className="min-h-0 flex-1">
          <Panel slotHeading="Files" elevation="high" density="compact">
            <Stack gap="density-xs" className="max-h-[560px] overflow-auto">
              {isLoading && <Loading description="Loading artifact files..." />}
              {files.map((file) => (
                <Button
                  key={file.path}
                  kind={selectedPath === file.path ? 'primary' : 'tertiary'}
                  size="small"
                  className="justify-start"
                  onClick={() => setSelectedPath(file.path)}
                >
                  {file.path}
                </Button>
              ))}
            </Stack>
          </Panel>
          <div className="xl:col-span-2 min-h-[560px]">
            {selectedPath ? (
              <FilesetFilePreviewContent
                workspace={fileset.workspace}
                filesetName={fileset.name}
                filePath={selectedPath}
                hideHeader
              />
            ) : (
              <Flex align="center" justify="center" className="h-full text-secondary">
                Select an artifact to preview.
              </Flex>
            )}
          </div>
        </Grid>
      )}
    </Stack>
  );
};

export const OptimizerEvalAuthorRunRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { insightId = '', evalAuthorRunId = '' } = useParams<{
    insightId: string;
    evalAuthorRunId: string;
  }>();
  const {
    data: run,
    isLoading,
    isError,
    refetch,
  } = useOptimizerGetEvalAuthorRun(workspace, evalAuthorRunId, {
    query: {
      refetchInterval: (query) => (isTerminal(query.state.data) ? false : 5_000),
    },
  });

  useBreadcrumbs({
    items: [
      { href: getOptimizerRoute(workspace), slotLabel: 'Insights' },
      { href: getOptimizerInsightRoute(workspace, insightId), slotLabel: 'Insight' },
      { slotLabel: run?.name ?? evalAuthorRunId },
    ],
  });

  if (isLoading && !run) return <Loading description="Loading Eval Author run..." />;
  if (isError || !run) {
    return (
      <Stack padding="density-2xl">
        <ErrorMessage
          header="Failed to load Eval Author run"
          message="The run may not exist or its workspace is unavailable."
          slotFooter={
            <Button kind="tertiary" onClick={() => void refetch()}>
              Retry
            </Button>
          }
        />
      </Stack>
    );
  }

  return (
    <AccessibleTitle title={`Eval Author run - ${run.name}`}>
      <Stack className="h-full min-h-0 overflow-auto p-density-2xl" gap="density-xl">
        <PageHeader
          className="p-0"
          slotHeading={run.name}
          slotDescription="Verifier-authoring lifecycle, model request, trajectory, generated code, and datasets."
          slotActions={<EvalAuthorRunStatusBadge status={run.status} />}
        />
        <TabsRoot defaultValue="overview" className="min-h-0">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="prompt">Prompt</TabsTrigger>
            <TabsTrigger value="verifier">Verifier</TabsTrigger>
            <TabsTrigger value="data">Data</TabsTrigger>
            <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="p-0">
            <OverviewTab run={run} />
          </TabsContent>
          <TabsContent value="prompt" className="p-0">
            <PromptTab run={run} />
          </TabsContent>
          <TabsContent value="verifier" className="p-0">
            <VerifierTab run={run} />
          </TabsContent>
          <TabsContent value="data" className="p-0">
            <DataTab run={run} />
          </TabsContent>
          <TabsContent value="artifacts" className="p-0">
            <ArtifactsTab run={run} />
          </TabsContent>
        </TabsRoot>
      </Stack>
    </AccessibleTitle>
  );
};
