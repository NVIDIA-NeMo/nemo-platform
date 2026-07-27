// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { entityNameSchema } from '@nemo/common/src/utils/entityName';
import { FilesetPurpose } from '@nemo/sdk/generated/platform/schema';
import { FilesCreateFilesetBody } from '@nemo/sdk/generated/platform/zod/files';
import { DATASET_TYPE_CUSTOM, DATASET_TYPE_SAMPLE } from '@studio/routes/FilesetNewRoute/constants';
import { z } from 'zod';

/**
 * Override the SDK-generated name validation. The generated zod uses the Files
 * service DTO's loose pattern (`^[\w\-.]+$`, max 255); the entity store
 * downstream enforces a stricter RFC-1035-ish pattern. Validate against the
 * strict pattern here so the user sees a useful inline error instead of a 422.
 */
export const DatasetCreateFilesetFormSchema = FilesCreateFilesetBody.extend({
  name: z.string().trim().pipe(entityNameSchema('Name')),
  purpose: z.nativeEnum(FilesetPurpose),
});

export type CreateFilesetFormFields = z.infer<typeof DatasetCreateFilesetFormSchema>;

/** Form extends schema with optional files (Upload/sample) and external storage inputs (url/secretKey). */
export type DatasetFormFields = CreateFilesetFormFields & {
  files?: File[];
  url?: string;
  secretKey?: string;
};

export type DatasetType = typeof DATASET_TYPE_CUSTOM | typeof DATASET_TYPE_SAMPLE;
