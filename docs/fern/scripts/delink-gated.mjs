// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Delink references from published pages into gated (unready) pages.
//
// Gated pages are .mdx files that exist in the repo but are intentionally left
// out of versions/latest.yml so Fern never builds them (they 404 / aren't
// indexed). A link from a *published* page into a gated page is therefore a
// dead link. The old MkDocs hide_unready_docs hook rewrote such links to plain
// text on every build; Fern has no equivalent hook, so this script reproduces
// that behavior:
//
//   node scripts/delink-gated.mjs            # check: list inbound links into gated pages, exit 1 if any
//   node scripts/delink-gated.mjs --fix      # rewrite those links to plain text in place
//
// "Gated" is derived from the nav, not a hand-maintained list: any .mdx not
// referenced in versions/latest.yml is gated. Publishing a feature (adding its
// pages back to the nav) automatically makes its inbound links valid again, so
// `--check` stops flagging them.

import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const FERN_DIR = resolve(SCRIPT_DIR, "..");
const REPO_DOCS = resolve(FERN_DIR, "..");              // docs/
const NAV = join(FERN_DIR, "versions", "latest.yml");
const FIX = process.argv.includes("--fix");

// --- published pages: every `path:` referenced in the nav -------------------
const navText = readFileSync(NAV, "utf8");
const published = new Set();
for (const m of navText.matchAll(/path:\s*(\S+\.mdx)\s*$/gm)) {
  published.add(resolve(dirname(NAV), m[1]));
}

// --- all doc pages (exclude the fern config/snippets tree) ------------------
function walk(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (p === FERN_DIR) continue; // skip docs/fern (config, components, snippets)
      walk(p, out);
    } else if (e.name.endsWith(".mdx")) {
      out.push(p);
    }
  }
  return out;
}
const allPages = walk(REPO_DOCS);
const isGated = (absMdx) => existsSync(absMdx) && !published.has(absMdx);

// resolve a link target (relative .md/.mdx, optional #anchor) from a source file
function resolveTarget(srcFile, target) {
  const t = target.trim();
  if (/^(https?:|mailto:|tel:|#|\/)/.test(t)) return null; // external / absolute / anchor
  const path = t.split("#")[0];
  if (!path) return null;
  const base = path.replace(/\.(md|mdx)$/, "").replace(/\/$/, "");
  // not a doc link if it has some other extension (image, etc.)
  const last = base.split("/").pop();
  if (last.includes(".")) return null;
  const dir = dirname(srcFile);
  for (const cand of [resolve(dir, base) + ".mdx", resolve(dir, base, "index.mdx")]) {
    if (existsSync(cand)) return cand;
  }
  return null;
}

// markdown links [text](target) and JSX href="target"
const MD = /\[([^\]]+)\]\(([^)\s]+)\)/g;
const HREF = /\bhref=("|')([^"']+)\1/g;

let findings = [];
for (const file of allPages) {
  if (!published.has(file)) continue; // only published pages can produce dead inbound links
  let src = readFileSync(file, "utf8");
  let changed = false;

  src = src.replace(MD, (whole, text, target) => {
    const tgt = resolveTarget(file, target);
    if (tgt && isGated(tgt)) {
      findings.push({ file, kind: "markdown", target, text });
      changed = true;
      return text; // delink -> plain text
    }
    return whole;
  });

  // JSX hrefs (Cards/Buttons) can't be cleanly turned into plain text; report only.
  for (const m of src.matchAll(HREF)) {
    const tgt = resolveTarget(file, m[2]);
    if (tgt && isGated(tgt)) {
      findings.push({ file, kind: "jsx-href", target: m[2], text: null });
    }
  }

  if (FIX && changed) writeFileSync(file, src);
}

const md = findings.filter((f) => f.kind === "markdown");
const jsx = findings.filter((f) => f.kind === "jsx-href");

if (findings.length === 0) {
  console.log("delink-gated: no inbound links from published pages into gated pages.");
  process.exit(0);
}

const rel = (f) => relative(REPO_DOCS, f);
if (FIX) {
  console.log(`delink-gated: delinked ${md.length} markdown link(s) into gated pages:`);
  for (const f of md) console.log(`  ${rel(f.file)}: "${f.text}" -> plain text (was ${f.target})`);
} else {
  console.error(`delink-gated: ${md.length} markdown link(s) from published pages point into gated (unbuilt) pages.`);
  for (const f of md) console.error(`  ${rel(f.file)}: [${f.text}](${f.target})`);
  console.error(`\nRun \`npm run fix:gated-links\` to delink them to plain text (or publish the target by adding it to versions/latest.yml).`);
}
if (jsx.length) {
  console.error(`\n${jsx.length} component href(s) into gated pages need manual handling (Card/Button cannot auto-delink):`);
  for (const f of jsx) console.error(`  ${rel(f.file)}: href="${f.target}"`);
}
// In --fix mode, markdown links are resolved; only unfixable JSX hrefs should fail.
process.exit(FIX ? (jsx.length ? 1 : 0) : 1);
