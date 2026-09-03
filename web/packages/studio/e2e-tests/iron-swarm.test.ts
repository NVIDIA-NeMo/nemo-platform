// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Regression for every Iron Swarm plugin screen.
 *
 * Read-only by default: the suite asserts against whatever the target platform already holds and
 * opens dialogs without submitting them. Only the BYO test creates anything, and it removes what it
 * created. Nothing here drives a real war-game — a run takes tens of minutes and its outcome depends
 * on a model, so a browser test that waited for one would be slow *and* flaky.
 *
 * Requires a running platform with the plugin installed:
 *   VSERVICE_URL_STUDIO_UI=http://localhost:8080/studio/ pnpm test:e2e iron-swarm
 */

import { IronSwarmPage } from '@e2e-tests/pages/iron-swarm';
import { disableAuthForTest } from '@e2e-tests/utils/pageUtils';
import { expect, test as baseTest } from '@playwright/test';

const WORKSPACE = 'default';

interface TestFixtures {
  ironSwarm: IronSwarmPage;
}

const test = baseTest.extend<TestFixtures>({
  ironSwarm: async ({ page }, runFixture) => {
    await runFixture(new IronSwarmPage(page, WORKSPACE));
  },
});

test.beforeEach(async ({ page }) => {
  await disableAuthForTest(page);
});

test.describe('Iron Swarm plugin', () => {
  test('is discovered by Studio and mounts its nav entry', async ({ page, ironSwarm, request }) => {
    // The plugin contract, asserted at both ends: the service advertises a bundle, and Studio loads
    // it. A plugin appears only if its Python package is installed and dist/index.js exists, so this
    // failing means packaging, not UI.
    const response = await request.get('/apis/plugins');
    expect(response.ok()).toBeTruthy();
    const plugins: Array<{ name: string; bundleUrl: string | null }> = await response.json();
    const ironSwarmPlugin = plugins.find((plugin) => plugin.name === 'iron-swarm');

    expect(ironSwarmPlugin, 'iron-swarm is not installed on the target platform').toBeDefined();
    expect(ironSwarmPlugin?.bundleUrl).toBe('/plugin-ui/iron-swarm/index.js');

    await ironSwarm.gotoRuns();
    // The plugin's page title is rendered by KUI's PageHeader as text, not a heading role.
    await expect(page.getByText('Iron Swarm').first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Manifests' })).toBeVisible();
  });

  test('run list renders and links to a run', async ({ page, ironSwarm }) => {
    await ironSwarm.gotoRuns();
    await ironSwarm.waitForTable();

    // Rows navigate on click; the "Open row" button is an a11y affordance, not the hit target.
    test.skip(!(await ironSwarm.openFirstRow()), 'No runs on the target platform to open.');
    await expect(page).toHaveURL(/plugin\/iron-swarm\/iron-swarm-run-/);
  });

  test('manifest list renders and reaches the create form', async ({ page, ironSwarm }) => {
    await ironSwarm.gotoManifests();
    await ironSwarm.waitForTable();

    await page.getByRole('link', { name: /new manifest/i }).click();
    await expect(page).toHaveURL(/manifests\/new/);
  });

  test('create form validates the id and offers both sources', async ({ page, ironSwarm }) => {
    await ironSwarm.gotoNewManifest();

    await expect(ironSwarm.sourceToggle()).toBeVisible();
    await expect(ironSwarm.sourceToggle().getByText('Registered agent')).toBeVisible();
    await expect(ironSwarm.sourceToggle().getByText('Bring your own')).toBeVisible();

    // An empty id must be refused client-side; the server would 422 with a less useful message.
    await page.getByRole('button', { name: /create manifest/i }).click();
    await expect(page.getByText(/manifest id is required/i)).toBeVisible();
  });

  test('choosing BYO asks for a bundle instead of an agent', async ({ page, ironSwarm }) => {
    await ironSwarm.gotoNewManifest();
    await ironSwarm.chooseSource('Bring your own');

    // The two sources are exclusive: offering an agent picker here would suggest a target that the
    // project branch never reads.
    await expect(page.getByTestId('project-upload')).toBeVisible();
    await expect(page.getByLabel(/deployed agent/i)).toBeHidden();
  });

  test('manifest detail shows the target and opens the run dialog', async ({ page, ironSwarm }) => {
    await ironSwarm.gotoManifests();
    await ironSwarm.waitForTable();

    test.skip(!(await ironSwarm.openFirstRow()), 'No manifests on the target platform to open.');

    const runButton = page.getByRole('button', { name: /run war-game/i });
    await expect(runButton).toBeVisible({ timeout: 30_000 });
    await runButton.click();

    // Opened, not submitted — submitting would start a real war-game.
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  test('a BYO manifest renders without an agent reference', async ({ page, ironSwarm }) => {
    // A project manifest has no registered agent behind it. Any screen that assumes one renders
    // "undefined" here and nowhere else, so this is the assertion the registered-agent tests cannot
    // make.
    await ironSwarm.gotoManifest('byo-ledger');

    await expect(page.getByRole('button', { name: /run war-game/i })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(/undefined|\[object Object\]/)).toHaveCount(0);
  });

  test('run details renders its panels', async ({ page, ironSwarm }) => {
    await ironSwarm.gotoRuns();
    await ironSwarm.waitForTable();

    test.skip(!(await ironSwarm.openFirstRow()), 'No runs on the target platform to open.');

    // The run view is the plugin's most composed screen. Its swarm graph is the part worth
    // asserting: every phase of a war-game has a lane, so a missing lane means the run record and
    // the view disagree about what a run is made of.
    //
    // Every lane gets the same generous timeout. The graph lays out progressively, so giving only
    // the first assertion room to wait made the rest race the layout — the test then failed and
    // passed on retry, which is worse than not having it.
    for (const lane of ['ATTACKER SWARM', 'OPENSHELL SANDBOX', 'DEFENDER SWARM', 'VALIDATOR SWARM']) {
      await expect(page.getByText(lane)).toBeVisible({ timeout: 30_000 });
    }
  });
});
