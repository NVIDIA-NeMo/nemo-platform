// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { PageLayout } from '@studio/routes/PageLayout';
import { getWorkspaceIndexRoute } from '@studio/routes/utils';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { SIDE_NAV_OPEN_KEY } from '@studio/util/localStorage';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

const mockItems = [
  { id: 'projects', slotLabel: 'Projects', icon: 'ProjectsIcon', href: ROUTES.workspace.index },
  {
    id: 'customizations',
    slotLabel: 'Customizations',
    icon: 'CustomizationsIcon',
    href: ROUTES.workspace.customizationJobList,
  },
  {
    group: 'Evaluate',
    items: [
      {
        id: 'annotation',
        slotLabel: 'Annotation',
        subItems: [
          {
            id: 'entries',
            slotLabel: 'Entries',
          },
          {
            id: 'export-jobs',
            slotLabel: 'Export Jobs',
          },
        ],
      },
    ],
  },
];

/**
 * Renders an element within a router context at the project index route
 */
const renderWithProjectRoute = (element: React.ReactElement) => {
  const router = createMemoryRouter([{ path: ROUTES.workspace.index, element }], {
    initialEntries: [getWorkspaceIndexRoute(workspace1.workspace)],
  });
  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

/**
 * Fixes act warnings by awaiting and asserting the component is defined
 */
const importNavigationDrawer = async () => {
  let NavigationDrawer;
  await act(async () => {
    const { NavigationDrawer: NavigationDrawerComponent } =
      await import('@studio/components/Layouts/NavigationDrawer/index');
    expect(NavigationDrawerComponent).toBeDefined();
    NavigationDrawer = NavigationDrawerComponent;
  });
  return NavigationDrawer!;
};

describe('NavigationDrawer', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });
  describe('General functionality', () => {
    it('renders the navigation drawer with the correct buttons', async () => {
      const NavigationDrawer = await importNavigationDrawer();
      renderWithProjectRoute(<NavigationDrawer items={mockItems} />);
      expect(await screen.findByText('Projects')).toBeInTheDocument();
      expect(await screen.findByText('Customizations')).toBeInTheDocument();
      expect(await screen.findByText('Annotation')).toBeInTheDocument();
      expect(await screen.findByText('Entries')).toBeInTheDocument();
      expect(await screen.findByText('Export Jobs')).toBeInTheDocument();
    });

    it('respects the local storage if it exists', async () => {
      const NavigationDrawer = await importNavigationDrawer();

      // Mock getItem to return 'false', which will make drawer closed
      const prevLocalStorage = window.localStorage;
      const localStorageMock = {
        getItem: vi.fn().mockImplementation((key) => {
          if (key === SIDE_NAV_OPEN_KEY) {
            return 'false';
          }
          return null;
        }),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn(),
      };
      Object.defineProperty(window, 'localStorage', {
        value: localStorageMock,
      });
      renderWithProjectRoute(
        <PageLayout
          sideNav={(collapsed) => <NavigationDrawer items={mockItems} collapsed={collapsed} />}
        />
      );
      // Text is collapsed
      expect(screen.queryByText('Projects')).not.toBeInTheDocument();
      Object.defineProperty(window, 'localStorage', {
        value: prevLocalStorage,
      });
    });

    it('renders subitems and chevron open/close icons', async () => {
      const user = userEvent.setup();

      const NavigationDrawer = await importNavigationDrawer();
      renderWithProjectRoute(<NavigationDrawer items={mockItems} />);
      expect(await screen.findByText('Annotation')).toBeInTheDocument();
      expect(await screen.findByText('Entries')).toBeInTheDocument();
      expect(await screen.findByText('Export Jobs')).toBeInTheDocument();

      // KUI v1.0 collapsible uses native <details><summary> — find the summary via text.
      // eslint-disable-next-line testing-library/no-node-access
      const accordionTrigger = screen.getByText('Annotation').closest('summary');
      expect(accordionTrigger).not.toBeNull();

      // Starts expanded
      expect(accordionTrigger).toHaveAttribute('data-state', 'open');
      // eslint-disable-next-line testing-library/no-node-access
      expect(document.querySelector('.lucide-chevron-up')).toBeInTheDocument();

      // Clicking closes it (chevron-down icon visible)
      await user.click(accordionTrigger as HTMLElement);
      expect(accordionTrigger).toHaveAttribute('data-state', 'closed');
      // eslint-disable-next-line testing-library/no-node-access
      expect(document.querySelector('.lucide-chevron-down')).toBeInTheDocument();
    });
  });
});
