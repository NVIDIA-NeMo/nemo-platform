// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { baseTestConfig } from '@nemo/testing/react/config';
import tailwindPostcss from '@tailwindcss/postcss';
import react from '@vitejs/plugin-react';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import license, { type Dependency, type Person } from 'rollup-plugin-license';
import { visualizer } from 'rollup-plugin-visualizer';
import { loadEnv } from 'vite';
import mkcert from 'vite-plugin-mkcert';
import svgr from 'vite-plugin-svgr';
// vite does not know about vitest -- vitest config extends vite config
import { defineConfig, mergeConfig } from 'vitest/config';

interface PackageJson {
  readonly name?: string;
  readonly version?: string;
  readonly license?: string | { readonly type?: string };
  readonly author?: string | { readonly name?: string };
  readonly dependencies?: Record<string, string>;
}

interface LicenseReportDependency {
  readonly name: string | null;
  readonly version: string | null;
  readonly license: string | null;
  readonly author: string | Person | null;
  readonly licenseText: string | null;
}

const isCI = Boolean(process.env.CI);
const isProd = process.env.NODE_ENV === 'production';
const configDir = path.dirname(fileURLToPath(import.meta.url));
const commonPackageDir = path.resolve(configDir, '../common');
const licenseFileNames = [
  'LICENSE',
  'LICENSE.md',
  'LICENSE.txt',
  'LICENCE',
  'LICENCE.md',
  'LICENCE.txt',
  'COPYING',
  'COPYING.md',
  'COPYING.txt',
];

const readPackageJson = (packageJsonPath: string): PackageJson =>
  JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8')) as PackageJson;

const getPackageLicense = (packageJson: PackageJson): string | null => {
  if (typeof packageJson.license === 'string') return packageJson.license;
  if (packageJson.license?.type) return packageJson.license.type;
  return null;
};

const getPackageAuthor = (packageJson: PackageJson): string | null => {
  if (typeof packageJson.author === 'string') return packageJson.author;
  return packageJson.author?.name ?? null;
};

const readLicenseText = (packageDir: string): string | null => {
  const licenseFile = licenseFileNames.find((fileName) =>
    fs.existsSync(path.join(packageDir, fileName))
  );

  return licenseFile ? fs.readFileSync(path.join(packageDir, licenseFile), 'utf-8') : null;
};

const getInstalledPackageDir = (packageName: string, consumerPackageDir: string): string => {
  const packageJsonPath = path.join(
    consumerPackageDir,
    'node_modules',
    packageName,
    'package.json'
  );

  if (!fs.existsSync(packageJsonPath)) {
    throw new Error(`Unable to resolve ${packageName} from ${consumerPackageDir}`);
  }

  return path.dirname(fs.realpathSync(packageJsonPath));
};

// The plugin only reports packages it sees in the Studio bundle graph. Include
// Common's runtime dependencies so the Studio license artifact covers shared UI
// code that may be distributed before every component is imported by Studio.
const getCommonRuntimeLicenseDependencies = (): LicenseReportDependency[] => {
  const commonPackageJson = readPackageJson(path.join(commonPackageDir, 'package.json'));
  const dependencyNames = Object.keys(commonPackageJson.dependencies ?? {})
    .filter((dependencyName) => !dependencyName.startsWith('@nemo/'))
    .sort((first, second) => first.localeCompare(second));

  return dependencyNames.map((dependencyName) => {
    const dependencyDir = getInstalledPackageDir(dependencyName, commonPackageDir);
    const dependencyPackageJson = readPackageJson(path.join(dependencyDir, 'package.json'));

    return {
      name: dependencyPackageJson.name ?? dependencyName,
      version: dependencyPackageJson.version ?? null,
      license: getPackageLicense(dependencyPackageJson),
      author: getPackageAuthor(dependencyPackageJson),
      licenseText: readLicenseText(dependencyDir),
    };
  });
};

const getLicenseDependencyKey = (dependency: LicenseReportDependency): string =>
  `${dependency.name ?? 'Unknown'}@${dependency.version ?? 'Unknown'}`;

const mergeLicenseDependencies = (dependencies: Dependency[]): LicenseReportDependency[] => {
  const seen = new Set(dependencies.map(getLicenseDependencyKey));
  const commonRuntimeDependencies = getCommonRuntimeLicenseDependencies().filter((dependency) => {
    const key = getLicenseDependencyKey(dependency);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return [...dependencies, ...commonRuntimeDependencies];
};

const getAuthorName = (author: LicenseReportDependency['author']): string => {
  if (typeof author === 'string') return author;
  return author?.name ?? 'Unknown';
};

const formatLicenseDependency = (dependency: LicenseReportDependency): string => {
  const license = dependency.license || 'Unknown';
  const name = dependency.name || 'Unknown';
  const version = dependency.version || 'Unknown';
  const author = getAuthorName(dependency.author);
  const licenseText = dependency.licenseText || '';
  return `${name}@${version}\nLicense: ${license}\nAuthor: ${author}\n${licenseText ? `\n${licenseText}\n` : ''}${'='.repeat(80)}`;
};

const formatLicenseReport = (dependencies: Dependency[]): string =>
  mergeLicenseDependencies(dependencies).map(formatLicenseDependency).join('\n\n');

// https://vitejs.dev/config/
// eslint-disable-next-line import/no-default-export
export default defineConfig(({ mode }) => {
  // Load env file based on mode (e.g., .env.fastapi for --mode fastapi)
  const {
    VITE_BASE_URL,
    VITE_DEV_SERVER_HOST,
    VITE_PLATFORM_BASE_URL,
    VITE_PLATFORM_PROXY_DOMAIN,
  } = loadEnv(mode, './env');
  const devServerHost = VITE_DEV_SERVER_HOST?.trim() || 'localhost';
  // Use VITE_BASE_URL to host the app at a subpath (fast mode)
  const base = ['fastapi'].includes(mode) && VITE_BASE_URL ? `/${VITE_BASE_URL}` : '/';

  // Dev-server proxy: when VITE_PLATFORM_BASE_URL is empty the app issues
  // same-origin `/apis/...` requests, so the browser only ever talks to the
  // (HTTPS) dev server and Vite forwards to the plain-HTTP platform server-side.
  // This avoids Safari's mixed-content block on an HTTPS page calling http://.
  // Gated on VITE_PLATFORM_PROXY_DOMAIN so it stays opt-in per developer.
  const proxyDomain = VITE_PLATFORM_PROXY_DOMAIN?.trim();
  const shouldProxyPlatform = VITE_PLATFORM_BASE_URL?.trim() === '' && Boolean(proxyDomain);

  // Skip mkcert in tests/CI: it fetches GitHub API for releases and hits rate limits (403) in CI.
  const plugins = [
    react(),
    ...(process.env.VITEST || mode.includes('test') ? [] : [mkcert()]),
    svgr(),
  ];

  return mergeConfig(baseTestConfig, {
    envDir: './env',
    base,
    plugins,
    resolve: {
      tsconfigPaths: true,
    },
    build: {
      rolldownOptions: {
        plugins: [
          !isCI ? visualizer({ filename: 'dist/stats.html', gzipSize: true }) : undefined,
          license({
            thirdParty: {
              includePrivate: false,
              output: {
                file: 'dist/LICENSES.txt',
                template: formatLicenseReport,
              },
            },
          }),
        ],
      },
      sourcemap: isProd ? false : true,
    },
    css: {
      postcss: {
        plugins: [
          tailwindPostcss({
            base: '../../packages', // We need to tell postcss to look for code in workspace packages
          }),
        ],
      },
    },
    server: {
      host: devServerHost,
      port: 5173,
      ...(shouldProxyPlatform
        ? {
            proxy: {
              '/apis': {
                target: proxyDomain,
                changeOrigin: true,
                secure: false,
              },
            },
          }
        : {}),
    },
    worker: {
      format: 'es',
      plugins: () => [react()],
    },
    test: {
      globalSetup: '@nemo/testing/react/global-setup',
      setupFiles: ['@nemo/testing/react/setup', './vitest.setup.tsx'],
      testTimeout: isCI ? 60000 : 10000,
      hookTimeout: isCI ? 60000 : 10000,
      exclude: ['e2e-tests/**', 'node_modules'],
      coverage: {
        include: ['src/**/*.{js,jsx,ts,tsx}'],
        provider: 'v8',
        // In CI skip 'html' reporter to reduce memory; cobertura + text suffice for MR and logs
        reporter: isCI ? ['cobertura', 'text'] : ['cobertura', 'text', 'html', 'json'],
        reportsDirectory: '.test-reports/coverage',
      },
      outputFile: {
        junit: '.test-reports/junit/junit.xml',
      },
    },
  });
});
