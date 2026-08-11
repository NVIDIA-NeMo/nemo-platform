// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { logger } from '@nemo/common/src/utils/logger';
import { VERSION_SHA } from '@studio/constants/environment';

export const logVersion = async () => {
  if (VERSION_SHA) {
    logger.info(`Version: ${VERSION_SHA}`);
  }
};
