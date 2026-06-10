// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import { Loading } from '@studio/components/Layouts/Loading';
import { BreadcrumbsProvider } from '@studio/providers/breadcrumbs/BreadcrumbsProvider';
import { WorkersProvider } from '@studio/providers/workers/WorkersProvider';
import { WorkspaceProvider } from '@studio/providers/workspace';
import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';

export const RootLayout = () => {
  return (
    <WorkspaceProvider>
      <ToastProvider>
        <WorkersProvider>
          <BreadcrumbsProvider>
            <Suspense fallback={<Loading />}>
              <Outlet />
            </Suspense>
          </BreadcrumbsProvider>
        </WorkersProvider>
      </ToastProvider>
    </WorkspaceProvider>
  );
};
