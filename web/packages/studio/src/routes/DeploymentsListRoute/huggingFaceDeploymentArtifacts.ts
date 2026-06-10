/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

/**
 * Hugging Face–source fileset name created in `createHuggingFaceDeployment` inside
 * `useCreateDeploymentBySource`. Keep in sync when changing the wizard.
 */
export function huggingFaceSourceFilesetName(deploymentName: string): string {
  return `${deploymentName}-hf-src`;
}

export const HUGGING_FACE_DEPLOYMENT_SOURCE_FIELD = 'studio_deployment_source';
export const HUGGING_FACE_DEPLOYMENT_SOURCE_VALUE = 'huggingface';
