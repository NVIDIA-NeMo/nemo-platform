// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Keep in sync with VENDOR_EXTERNALS in web/packages/studio/vite.config.ts —
// Studio serves a single shared React/react-dom/router instance via an
// import map, and the plugin bundle must leave these as bare specifiers so
// the browser resolves them to that shared instance at runtime.
const STUDIO_SHARED_DEPS = [
  "react",
  "react/jsx-runtime",
  "react-dom",
  "react-dom/client",
  "react-router",
  // Studio's design system, shared via the import map so the plugin's KUI
  // components use Studio's single foundations instance and theme.
  "@nvidia/foundations-react-core",
  // Shared so the plugin's useQuery uses Studio's QueryClient (one cache).
  "@tanstack/react-query",
  // Studio's shared UI. Bare specifier only — deep paths aren't mapped.
  "@nemo/common",
];

// Prepended to the built bundle so the emitted artifact keeps an SPDX header —
// minification strips source comments, and CI's copyright-header check
// (script/copyright_fixer.py) requires the header literally in the file.
const LICENSE_BANNER =
  "// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n" +
  "// SPDX-License-Identifier: Apache-2.0";

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: "src/index.ts",
      formats: ["es"],
      fileName: () => "index.js",
    },
    // Build into the Python package so it gets included in wheel installs
    outDir: "../src/nemo_example_plugin/web/dist",
    emptyOutDir: true,
    rolldownOptions: {
      external: STUDIO_SHARED_DEPS,
      output: {
        banner: LICENSE_BANNER,
      },
    },
  },
});
