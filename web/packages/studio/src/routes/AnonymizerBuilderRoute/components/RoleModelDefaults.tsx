// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useDefaultRoleModels } from '@studio/routes/AnonymizerBuilderRoute/useDefaultRoleModels';
import { FC } from 'react';

/** Seeds role model defaults from inside the form provider, independent of the active tab. */
export const RoleModelDefaults: FC = () => {
  useDefaultRoleModels();
  return null;
};
