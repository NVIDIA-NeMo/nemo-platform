// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { RadioCard } from '@nemo/common/src/components/RadioCard';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  filesUploadFile,
  getFilesListFilesetFilesQueryKey,
  getFilesListFilesetsQueryKey,
  getFilesRetrieveFilesetQueryKey,
  useFilesCreateFileset,
} from '@nemo/sdk/generated/platform/api';
import {
  FilesetOutput,
  FilesetPurpose,
  CreateFilesetRequest,
} from '@nemo/sdk/generated/platform/schema';
import {
  FilesCreateFilesetBody,
  filesCreateFilesetBodyNameMax,
  filesCreateFilesetBodyNameRegExp,
} from '@nemo/sdk/generated/platform/zod/files';
import {
  Badge,
  Block,
  Button,
  Card,
  Flex,
  Grid,
  GridItem,
  RadioGroupRoot,
  SegmentedControl,
  SidePanel,
  Stack,
  TabsContent,
  TabsTrigger,
  TabsRoot,
  Text,
  TabsList,
  Upload,
} from '@nvidia/foundations-react-core';
import { getErrorMessage as getApiErrorMessage } from '@studio/api/common/utils';
import { useSampleDatasetFiles } from '@studio/api/datasets/useSampleDatasetFiles';
import { FILESET_DETAILS_ENABLED } from '@studio/constants/environment';
import { SAMPLE_DATASETS, SampleDataset } from '@studio/constants/sampleDatasets';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { CreateSecretModal } from '@studio/routes/SecretsListRoute/CreateSecretModal';
import { SecretSearchableSelect } from '@studio/routes/SecretsListRoute/SecretSearchableSelect';
import {
  getDatasetDetailRoute,
  getFilesetDetailsRoute,
  getModelDetailRoute,
  getWorkspaceFilesetsRoute,
} from '@studio/routes/utils';
import { handleFormErrorsGeneric } from '@studio/util/forms/error';
import {
  isHuggingFaceUrl,
  isNgcUrl,
  storageConfigFromUrl,
} from '@studio/util/storageConfigFromUrl';
import { QueryObserverResult, useQueryClient } from '@tanstack/react-query';
import { FileCheck } from 'lucide-react';
import { FC, useCallback, useMemo, useRef, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

const DATASET_NAME_REQUIRED_MESSAGE =
  'Name is required. Use lowercase letters, numbers, hyphens, underscores, and dots (for example my-fileset).';

const DATASET_NAME_PATTERN_MESSAGE =
  'Name may only contain letters, numbers, underscores, hyphens, and dots.';

/** Per-purpose copy shown in the purpose selector. Kept adjacent to the enum so each value has user-facing explanation. */
const PURPOSE_OPTIONS: {
  value: FilesetPurpose;
  label: string;
  description: string;
}[] = [
  {
    value: FilesetPurpose.generic,
    label: 'Generic',
    description:
      "Default. Use for files that don't fit the Dataset or Model categories. Doesn't add purpose-specific metadata fields.",
  },
  {
    value: FilesetPurpose.dataset,
    label: 'Dataset',
    description:
      'For training and evaluation data. Enables dataset-specific metadata, including schema information.',
  },
  {
    value: FilesetPurpose.model,
    label: 'Model',
    description:
      'For model weights and checkpoints. Enables model-specific metadata, including tool-calling and model configuration fields.',
  },
];

/**
 * Same as API schema with clearer validation messages for the name field (empty name otherwise
 * yields a generic regex error). `description` is intentionally not overridden — the base schema
 * already has it as `z.string().optional()` with no length cap, matching the server.
 */
const DatasetCreateFilesetFormSchema = FilesCreateFilesetBody.extend({
  name: z
    .string()
    .trim()
    .min(1, DATASET_NAME_REQUIRED_MESSAGE)
    .max(filesCreateFilesetBodyNameMax)
    .regex(filesCreateFilesetBodyNameRegExp, DATASET_NAME_PATTERN_MESSAGE),
  purpose: z.nativeEnum(FilesetPurpose),
});

type CreateFilesetFormFields = z.infer<typeof DatasetCreateFilesetFormSchema>;

/** Form extends schema with optional files (Upload/sample) and external storage inputs (url/secretKey). */
type DatasetFormFields = CreateFilesetFormFields & {
  files?: File[];
  url?: string;
  secretKey?: string;
};

const DATASET_TYPE_CUSTOM = 'custom';
const DATASET_TYPE_SAMPLE = 'sample';
type DatasetType = typeof DATASET_TYPE_CUSTOM | typeof DATASET_TYPE_SAMPLE;

function getSampleDatasetName(workspace: string, sampleId: string): string {
  const truncatedProjectName = workspace.split('-')[1] || workspace;
  return `${sampleId}-${truncatedProjectName}`;
}

/**
 * User-facing error for external storage create failure, with a stable prefix per storage type
 * so the toast never shows raw [object Object] from API detail.
 */
function getExternalStorageCreateErrorMessage(err: unknown, externalUrl: string): string {
  let prefix: string;
  try {
    const parsed = new URL(externalUrl);
    if (isNgcUrl(parsed)) {
      prefix = 'Failed to create fileset from NGC. ';
    } else if (isHuggingFaceUrl(parsed)) {
      prefix = 'Failed to create fileset from Hugging Face. ';
    } else {
      prefix = 'Failed to create fileset from external storage. ';
    }
  } catch {
    prefix = 'Failed to create fileset from external storage. ';
  }
  const detail =
    err && typeof err === 'object'
      ? getApiErrorMessage(err as Error, 'Please check your URL and credentials.')
      : 'Please check your URL and credentials.';
  return prefix + detail;
}

/** Normalize form files (may be File[] or KUI Upload's FileUploadItem[]) to File[]. */
function toFileList(value: unknown): File[] {
  if (!value) return [];
  const arr = Array.isArray(value) ? value : [value];
  return arr.flatMap((item) =>
    item instanceof File
      ? [item]
      : (item as { file?: File }).file
        ? [(item as { file: File }).file]
        : []
  );
}

export const FilesetNewRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const [activeTab, setActiveTab] = useState<DatasetType>(DATASET_TYPE_CUSTOM);
  const [selectedSampleDataset, setSelectedSampleDataset] = useState<SampleDataset>(
    SAMPLE_DATASETS[0]
  );
  const [isSubmitPending, setIsSubmitPending] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const sampleFilesRef = useRef<Promise<QueryObserverResult<File[], Error>> | null>(null);

  const [storageTab, setStorageTab] = useState<'local' | 'external'>('local');
  const [createSecretModalOpen, setCreateSecretModalOpen] = useState(false);

  const {
    control,
    handleSubmit,
    setValue,
    getValues,
    watch,
    formState: { errors },
  } = useForm<DatasetFormFields>({
    resolver: zodResolver(DatasetCreateFilesetFormSchema),
    defaultValues: {
      name: '',
      description: '',
      files: undefined,
      url: '',
      secretKey: '',
      // Default chosen for least surprise: the page previously hardcoded purpose=dataset.
      purpose: FilesetPurpose.dataset,
    },
    mode: 'onChange',
  });

  const url = watch('url');
  const selectedSecretName = watch('secretKey');
  const secretKeyLabel = useMemo(() => {
    if (!url?.trim()) return 'Secret Key';
    try {
      if (isHuggingFaceUrl(new URL(url))) return 'HuggingFace Token (optional)';
      if (isNgcUrl(new URL(url))) return 'NGC API Key';
    } catch {
      // invalid URL
    }
    return 'Secret Key';
  }, [url]);

  const { refetch: fetchSampleFiles } = useSampleDatasetFiles({
    sampleDataset: selectedSampleDataset,
    enabled: false,
  });

  const { mutateAsync: createFileset } = useFilesCreateFileset({
    mutation: {
      onSuccess: (fileset) => {
        queryClient.resetQueries({ queryKey: getFilesListFilesetsQueryKey(fileset.workspace) });
        queryClient.resetQueries({
          queryKey: getFilesRetrieveFilesetQueryKey(fileset.workspace, fileset.name),
        });
        queryClient.resetQueries({
          queryKey: getFilesListFilesetFilesQueryKey(fileset.workspace, fileset.name),
        });
      },
    },
  });

  /** Step: create fileset. Present failures to user in caller. */
  const createFilesetStep = useCallback(
    async (workspace: string, data: CreateFilesetRequest): Promise<FilesetOutput> => {
      const fileset: FilesetOutput = await createFileset({
        workspace,
        data: {
          name: data.name,
          description: data.description ?? '',
          project: data.project,
          storage: data.storage ?? undefined,
          purpose: data.purpose ?? FilesetPurpose.generic,
          metadata: data.metadata,
          custom_fields: data.custom_fields,
          cache: data.cache,
        },
      });
      return fileset;
    },
    [createFileset]
  );

  /** Step: upload files to dataset. Present failures to user in caller. */
  const uploadFilesToDatasetStep = useCallback(
    async (workspace: string, fileset: FilesetOutput, files: File[]): Promise<void> => {
      await Promise.all(
        files.map(async (file) => {
          const blob = new Blob([await file.arrayBuffer()], {
            type: file.type || 'application/octet-stream',
          });
          return filesUploadFile(workspace, fileset.name, file.name, blob);
        })
      );
    },
    []
  );

  // Sync hidden name/description when a sample is selected (sample tab = simulated local form)
  const handleSelectSample = useCallback(
    (dataset: SampleDataset) => {
      setSelectedSampleDataset(dataset);
      setValue('name', getSampleDatasetName(workspace, dataset.id), { shouldValidate: false });
      setValue('description', dataset.description ?? '', { shouldValidate: false });
    },
    [workspace, setValue]
  );

  // When switching tabs, reset the opposite tab’s form state so we don’t leak values
  const handleTabChange = useCallback(
    (value: DatasetType) => {
      setActiveTab(value);
      if (value === DATASET_TYPE_CUSTOM) {
        setValue('name', '', { shouldValidate: false });
        setValue('description', '', { shouldValidate: false });
        setValue('files', undefined, { shouldValidate: false });
        sampleFilesRef.current = null;
      } else {
        setValue('name', getSampleDatasetName(workspace, selectedSampleDataset.id), {
          shouldValidate: false,
        });
        setValue('description', selectedSampleDataset.description ?? '', {
          shouldValidate: false,
        });
        setValue('files', undefined, { shouldValidate: false });
        sampleFilesRef.current = fetchSampleFiles();
      }
    },
    [
      setValue,
      workspace,
      selectedSampleDataset.id,
      selectedSampleDataset.description,
      fetchSampleFiles,
    ]
  );

  const onSubmit = useCallback(
    async (data: DatasetFormFields) => {
      const { success, error } = DatasetCreateFilesetFormSchema.safeParse(data);
      if (!success) {
        toast.error(error.message);
        return;
      }

      setIsSubmitPending(true);

      // Step 1 (sample only): fetch sample files via lazy query
      let files: File[];
      if (activeTab === DATASET_TYPE_SAMPLE) {
        if (!sampleFilesRef.current) {
          toast.error('No sample files could be loaded.');
          setIsSubmitPending(false);
          return;
        }
        const result = (await sampleFilesRef.current) as QueryObserverResult<File[], Error>;
        if (result.isError || result.error) {
          toast.error(getApiErrorMessage(result.error as Error, 'Failed to load sample files'));
          setIsSubmitPending(false);
          return;
        }
        if (!result.data?.length) {
          toast.error('No sample files could be loaded.');
          setIsSubmitPending(false);
          return;
        }
        files = result.data;
      } else {
        files = toFileList(getValues('files'));
      }

      // Step 2: create fileset. Sample tab always produces a dataset-purpose fileset
      // (preconfigured samples are training/eval data by definition); Custom tab
      // uses whatever the user picked in the Purpose selector.
      const effectivePurpose =
        activeTab === DATASET_TYPE_SAMPLE ? FilesetPurpose.dataset : data.purpose;
      let createPayload: CreateFilesetRequest = {
        name: data.name,
        description: data.description ?? '',
        project: data.project,
        storage: data.storage ?? undefined,
        purpose: effectivePurpose,
        metadata: data.metadata,
        custom_fields: data.custom_fields,
        cache: data.cache,
      };
      const url = getValues('url');
      const secretRef = getValues('secretKey')?.trim() || undefined;
      if (storageTab === 'external' && url?.trim()) {
        try {
          createPayload = {
            ...createPayload,
            storage: storageConfigFromUrl({
              url: url.trim(),
              secretKey: secretRef,
            }),
          };
        } catch (e) {
          toast.error(
            e instanceof Error
              ? e.message
              : 'Invalid external storage URL or credential. For NGC, select a secret with your API key.'
          );
          setIsSubmitPending(false);
          return;
        }
      }

      let fileset: FilesetOutput;
      try {
        fileset = await createFilesetStep(workspace, createPayload);
      } catch (err) {
        const message =
          storageTab === 'external' && url?.trim()
            ? getExternalStorageCreateErrorMessage(err, url.trim())
            : getApiErrorMessage(err as Error, 'Failed to create fileset');
        toast.error(message);
        setIsSubmitPending(false);
        return;
      }

      // Step 3: upload files to dataset
      if (files.length) {
        try {
          await uploadFilesToDatasetStep(workspace, fileset, files);
        } catch (err) {
          toast.error(getApiErrorMessage(err as Error, 'Failed to upload files'));
          setIsSubmitPending(false);
          return;
        }
      }

      setIsSubmitPending(false);
      if (FILESET_DETAILS_ENABLED && fileset.purpose === FilesetPurpose.dataset) {
        navigate(getDatasetDetailRoute(workspace, fileset.name));
        return;
      }
      if (FILESET_DETAILS_ENABLED && fileset.purpose === FilesetPurpose.model) {
        navigate(getModelDetailRoute(workspace, fileset.name));
        return;
      }
      navigate(
        getFilesetDetailsRoute(
          workspace,
          getEntityReference(fileset, { encode: true }),
          undefined,
          true
        )
      );
    },
    [
      activeTab,
      createFilesetStep,
      getValues,
      navigate,
      storageTab,
      toast,
      uploadFilesToDatasetStep,
      workspace,
    ]
  );

  const handleClose = useCallback(() => {
    navigate(getWorkspaceFilesetsRoute(workspace));
  }, [navigate, workspace]);

  const handleSecretCreated = useCallback(
    (secretName: string) => {
      setValue('secretKey', secretName, { shouldValidate: true });
    },
    [setValue]
  );

  return (
    <>
      <SidePanel
        slotHeading="Create Fileset"
        side="right"
        open
        onOpenChange={handleClose}
        className="max-w-[600px] w-full"
        bordered
        modal
        slotFooter={
          <>
            <Button kind="tertiary" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              type="button"
              color="brand"
              disabled={isSubmitPending}
              onClick={handleSubmit(
                onSubmit,
                handleFormErrorsGeneric({ title: 'Fileset New Form Errors' })
              )}
            >
              {isSubmitPending ? 'Creating Fileset...' : 'Create Fileset'}
            </Button>
          </>
        }
      >
        <Stack className="h-full overflow-auto w-full" gap="density-xl">
          <SegmentedControl
            size="tiny"
            className="w-full"
            value={activeTab}
            onValueChange={(value) => handleTabChange(value as DatasetType)}
            items={[
              { value: DATASET_TYPE_CUSTOM, children: 'Custom Fileset' },
              { value: DATASET_TYPE_SAMPLE, children: 'Sample Dataset' },
            ]}
          />
          {activeTab === DATASET_TYPE_CUSTOM && (
            <>
              <Text kind="body/regular/md">
                Filesets organize files by purpose. Pick a purpose to control which metadata fields
                are available, give the fileset a name, and choose where its files live.
              </Text>
              <form
                onSubmit={handleSubmit(
                  onSubmit,
                  handleFormErrorsGeneric({ title: 'Fileset New Form Errors' })
                )}
              >
                <Stack gap="density-2xl">
                  <Flex direction="col" gap="density-lg">
                    <ControlledTextInput
                      label="Fileset Name"
                      disabled={isSubmitPending}
                      autoFocus
                      useControllerProps={{
                        name: 'name',
                        control,
                      }}
                    />

                    <ControlledTextArea
                      label="Description (optional)"
                      disabled={isSubmitPending}
                      useControllerProps={{ name: 'description', control }}
                    />
                  </Flex>

                  <Flex direction="col" gap="density-lg" className="w-full min-w-0">
                    <Text kind="label/bold/lg">Purpose</Text>
                    <Text kind="body/regular/md">
                      Purpose determines which metadata fields are available and can&apos;t be
                      changed after the fileset is created.
                    </Text>
                    <Controller
                      control={control}
                      name="purpose"
                      render={({ field }) => (
                        <RadioGroupRoot
                          name={field.name}
                          className="w-full"
                          value={field.value}
                          onValueChange={(value) => field.onChange(value as FilesetPurpose)}
                        >
                          <Grid gap="density-md" cols={1}>
                            {PURPOSE_OPTIONS.map((option) => (
                              <RadioCard
                                key={option.value}
                                value={option.value}
                                label={option.label}
                                description={option.description}
                              />
                            ))}
                          </Grid>
                        </RadioGroupRoot>
                      )}
                    />
                  </Flex>

                  <Flex direction="col" gap="density-lg" className="w-full min-w-0">
                    <Text kind="label/bold/lg">Source</Text>
                    <Text kind="body/regular/md">
                      Upload files for local read/write access, or provide a URL and a workspace
                      secret for external read-only access.
                    </Text>

                    <TabsRoot
                      className="w-full min-w-0"
                      value={storageTab}
                      onValueChange={(value) => {
                        const next = value as 'local' | 'external';
                        setStorageTab(next);
                        if (next === 'local') {
                          setValue('url', '', { shouldValidate: false });
                          setValue('secretKey', '', { shouldValidate: false });
                        }
                      }}
                    >
                      <TabsList>
                        <TabsTrigger value="local">Upload</TabsTrigger>
                        <TabsTrigger value="external">External</TabsTrigger>
                      </TabsList>
                      <TabsContent className="w-full min-w-0 p-0 items-stretch" value="local">
                        <Upload
                          accept="text/csv,text/json,.jsonl,.parquet"
                          multiple
                          onValueChange={(files) => {
                            const list = Array.isArray(files) ? files : files ? [files] : undefined;
                            setValue('files', toFileList(list), { shouldValidate: false });
                          }}
                        >
                          Supports JSONL, CSV, and Parquet files up to 50 MB.
                        </Upload>
                      </TabsContent>
                      <TabsContent className="w-full min-w-0 p-0 items-stretch" value="external">
                        <Stack gap="density-lg" className="w-full min-w-0">
                          <ControlledTextInput
                            label="URL"
                            disabled={isSubmitPending}
                            useControllerProps={{ name: 'url', control }}
                          />
                          <SecretSearchableSelect
                            workspace={workspace}
                            queryEnabled={
                              activeTab === DATASET_TYPE_CUSTOM &&
                              storageTab === 'external' &&
                              Boolean(workspace)
                            }
                            ensureOptionValue={selectedSecretName || undefined}
                            useControllerProps={{ control, name: 'secretKey' }}
                            onRequestNewSecret={() => setCreateSecretModalOpen(true)}
                            triggerPlaceholder=""
                            formFieldProps={{
                              slotLabel: secretKeyLabel,
                              slotInfo:
                                'Select a secret that stores the credential for this URL, or choose New Secret to create one.',
                              slotError: errors.secretKey?.message,
                            }}
                          />
                        </Stack>
                      </TabsContent>
                    </TabsRoot>
                  </Flex>
                </Stack>
              </form>
            </>
          )}
          {activeTab === DATASET_TYPE_SAMPLE && (
            <>
              <Block>
                <Text kind="body/regular/md" className="block">
                  Choose from the following pre-configured sample datasets.
                </Text>
              </Block>
              <Grid gap="density-md" cols={2}>
                {SAMPLE_DATASETS.map((dataset) => (
                  <GridItem key={dataset.id}>
                    <Card
                      interactive
                      selected={selectedSampleDataset.id === dataset.id}
                      onClick={() => handleSelectSample(dataset)}
                      className="cursor-pointer shadow-none!"
                      slotHeader={
                        <Badge kind="solid" color="purple">
                          <FileCheck />
                          Sample Dataset
                        </Badge>
                      }
                    >
                      <Flex gap="density-sm" direction="col">
                        <Text kind="label/bold/md">{dataset.name}</Text>
                        <Text kind="body/regular/md">{dataset.description}</Text>
                      </Flex>
                    </Card>
                  </GridItem>
                ))}
              </Grid>
            </>
          )}
        </Stack>
      </SidePanel>
      <CreateSecretModal
        workspace={workspace}
        open={createSecretModalOpen}
        onClose={() => setCreateSecretModalOpen(false)}
        onSecretCreated={handleSecretCreated}
      />
    </>
  );
};
