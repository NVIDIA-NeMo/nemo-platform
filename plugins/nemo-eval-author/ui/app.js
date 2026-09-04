// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const REPORT_SCHEMA = "nemo.eval_author.audit_coverage_report.v1";
const ACTIONABLE_REASON = "not_covered_by_any_input_report";

const sampleReport = {
  schema: REPORT_SCHEMA,
  audit: {
    path: ".eval-author/audit.md",
    schema: "nemo.eval_author.audit.v1",
    agent: "support-agent",
    status: "draft",
    item_count: 5,
    item_counts: { capability: 1, failure_case: 1, tool: 3 },
  },
  measured_kinds: ["tool"],
  warnings: [],
  input_reports: [
    {
      path: ".eval-author/audit-measurements/task=account-recovery/run=trial-001/tool_calls/coverage.json",
      method: "tool_calls",
      item_kind: "tool",
      item_kind_count: 3,
      subject: {
        trace: ".harbor/runs/account-recovery/trials/trial-001/agent/trajectory.json",
        trace_format: "atif",
        task_id: "account-recovery",
        run_id: "trial-001",
      },
      covered: ["customer.lookup"],
      covered_count: 1,
    },
    {
      path: ".eval-author/audit-measurements/task=escalation/run=trial-002/tool_calls/coverage.json",
      method: "tool_calls",
      item_kind: "tool",
      item_kind_count: 3,
      subject: {
        trace: ".harbor/runs/escalation/trials/trial-002/agent/trajectory.json",
        trace_format: "atif",
        task_id: "escalation",
        run_id: "trial-002",
      },
      covered: ["ticket.create"],
      covered_count: 1,
    },
  ],
  coverage: {
    overall: { item_count: 5, covered_count: 2, uncovered_count: 3 },
    by_kind: {
      capability: { item_count: 1, covered_count: 0, uncovered_count: 1 },
      failure_case: { item_count: 1, covered_count: 0, uncovered_count: 1 },
      tool: { item_count: 3, covered_count: 2, uncovered_count: 1 },
    },
  },
  covered: ["customer.lookup", "ticket.create"],
  uncovered: ["password.reset", "account_recovery", "account_recovery_unverified_identity"],
  uncovered_items: [
    {
      name: "password.reset",
      kind: "tool",
      reason: ACTIONABLE_REASON,
      description: "Resets a verified customer's password.",
      source_refs: ["ethos:Tools"],
      generation: {
        focus:
          "Exercise a scenario where the agent should call password.reset: Used after identity is verified and the user requests password recovery.",
        needed_tools: ["password.reset"],
        evidence_required: [
          {
            kind: "tool_call",
            tool: "password.reset",
            description: "Trace shows a password.reset call after verification.",
          },
        ],
      },
      audit_item: {
        kind: "tool",
        name: "password.reset",
        expected_use: "Used after identity is verified and the user requests password recovery.",
      },
    },
    {
      name: "account_recovery",
      kind: "capability",
      reason: "not_measured_by_any_method",
      description: "Helps a verified user regain account access.",
      source_refs: ["ethos:Behavior"],
      generation: {
        focus:
          "Exercise capability account_recovery: Verify identity, inspect the account, reset access, and summarize the outcome.",
        needed_tools: ["customer.lookup", "password.reset"],
        evidence_required: [{ kind: "outcome", description: "Final response explains the account recovery result." }],
      },
      audit_item: { kind: "capability", name: "account_recovery" },
    },
    {
      name: "account_recovery_unverified_identity",
      kind: "failure_case",
      reason: "not_measured_by_any_method",
      description: "Refuses to reset access when identity verification is missing.",
      source_refs: ["ethos:Success Criteria"],
      generation: {
        focus:
          "Exercise failure case account_recovery_unverified_identity by triggering missing verification details.",
        needed_tools: ["customer.lookup"],
        evidence_required: [{ kind: "policy_boundary", description: "Agent refuses reset without verification." }],
      },
      audit_item: { kind: "failure_case", name: "account_recovery_unverified_identity" },
    },
  ],
};

const els = {
  file: document.querySelector("#file-input"),
  input: document.querySelector("#report-input"),
  toggleInput: document.querySelector("#toggle-input"),
  sample: document.querySelector("#sample-button"),
  message: document.querySelector("#message"),
  dashboard: document.querySelector("#dashboard"),
  agent: document.querySelector("#agent-name"),
  percent: document.querySelector("#coverage-percent"),
  coverageDetail: document.querySelector("#coverage-detail"),
  actionableCount: document.querySelector("#actionable-count"),
  measuredKinds: document.querySelector("#measured-kinds"),
  kindBars: document.querySelector("#kind-bars"),
  actionableGaps: document.querySelector("#actionable-gaps"),
  uncoveredCount: document.querySelector("#uncovered-count"),
  uncoveredItems: document.querySelector("#uncovered-items"),
};

let inputCollapsed = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function parseReport(text) {
  const report = JSON.parse(text);
  if (!report || typeof report !== "object" || Array.isArray(report)) {
    throw new Error("Expected one JSON object.");
  }
  if (report.schema !== REPORT_SCHEMA) {
    throw new Error(`Expected schema ${REPORT_SCHEMA}.`);
  }
  return report;
}

function coveragePercent(summary) {
  const itemCount = Number(summary?.item_count || 0);
  const coveredCount = Number(summary?.covered_count || 0);
  if (!itemCount) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((coveredCount / itemCount) * 100)));
}

function coverageLabel(summary) {
  const itemCount = Number(summary?.item_count || 0);
  const coveredCount = Number(summary?.covered_count || 0);
  if (!itemCount) {
    return { detail: "0 denominator items", percent: "n/a" };
  }
  return {
    detail: `${coveredCount} of ${itemCount} audit items`,
    percent: `${coveragePercent(summary)}%`,
  };
}

function taskSlugForTool(toolName) {
  let slugBody = String(toolName || "")
    .trim()
    .replaceAll(".", "-")
    .replaceAll(":", "-")
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  if (!slugBody) {
    slugBody = "tool";
  } else if (!/^[a-z]/.test(slugBody)) {
    slugBody = `tool-${slugBody}`;
  }
  return `cover-${slugBody}`;
}

function artifactPaths(taskSlug) {
  return {
    proposal: `.eval-author/proposals/${taskSlug}-instruction.md`,
    draft: `.eval-author/task-drafts/${taskSlug}`,
    measurements: `.eval-author/task-measurements/${taskSlug}`,
    taskId: taskSlug,
  };
}

function actionableTools(report) {
  const assigned = new Set();
  return (report.uncovered_items || [])
    .filter((item) => item.kind === "tool" && item.reason === ACTIONABLE_REASON)
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((item) => {
      const base = taskSlugForTool(item.name);
      let slug = base;
      let suffix = 2;
      while (assigned.has(slug)) {
        slug = `${base}-${suffix}`;
        suffix += 1;
      }
      assigned.add(slug);
      return { ...item, task_slug: slug, paths: artifactPaths(slug) };
    });
}

function renderList(items, empty = "None reported.") {
  if (!items?.length) {
    return `<p>${escapeHtml(empty)}</p>`;
  }
  return `<ul class="mini-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderEvidence(items = []) {
  if (!items.length) {
    return "";
  }
  return renderList(
    items.map((item) => {
      const tool = item.tool ? ` ${item.tool}:` : "";
      return `${item.kind || "evidence"}${tool} ${item.description || JSON.stringify(item)}`;
    }),
  );
}

function renderKindBars(report) {
  const kinds = ["tool", "capability", "failure_case"];
  els.kindBars.innerHTML = kinds
    .map((kind) => {
      const summary = report.coverage?.by_kind?.[kind] || { item_count: 0, covered_count: 0, uncovered_count: 0 };
      const value = coveragePercent(summary);
      return `
        <div class="kind-row">
          <strong>${escapeHtml(kind.replace("_", " "))}</strong>
          <div class="bar-track" aria-label="${escapeHtml(kind)} ${value}% covered">
            <div class="bar-fill" style="--coverage-width: ${value}%"></div>
          </div>
          <span>${summary.covered_count}/${summary.item_count} covered</span>
        </div>
      `;
    })
    .join("");
}

function renderActionableGaps(gaps) {
  if (!gaps.length) {
    els.actionableGaps.innerHTML =
      '<article class="info-card"><p>No uncovered tool gaps are actionable for task creation.</p></article>';
    return;
  }
  els.actionableGaps.innerHTML = gaps
    .map((gap) => {
      const neededTools = gap.generation?.needed_tools || [];
      const evidence = gap.generation?.evidence_required || [];
      return `
        <article class="gap-card">
          <div class="gap-heading">
            <h3><code>${escapeHtml(gap.name)}</code></h3>
            <span class="tag tool">${escapeHtml(gap.task_slug)}</span>
          </div>
          <p>${escapeHtml(gap.generation?.focus || gap.description)}</p>
          <div class="gap-meta">
            <span class="pill">reason: ${escapeHtml(gap.reason)}</span>
            <span class="pill">needed: ${escapeHtml(neededTools.join(", ") || "none")}</span>
          </div>
          <div class="path-grid">
            <div class="path-card"><span>proposal</span><code>${escapeHtml(gap.paths.proposal)}</code></div>
            <div class="path-card"><span>draft</span><code>${escapeHtml(gap.paths.draft)}</code></div>
            <div class="path-card"><span>measurements</span><code>${escapeHtml(gap.paths.measurements)}</code></div>
            <div class="path-card"><span>task id</span><code>${escapeHtml(gap.paths.taskId)}</code></div>
          </div>
          ${evidence.length ? `<div>${renderEvidence(evidence)}</div>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderUncoveredItems(report) {
  const items = report.uncovered_items || [];
  els.uncoveredCount.textContent = `${items.length} gaps`;
  if (!items.length) {
    els.uncoveredItems.innerHTML = '<article class="info-card"><p>Everything in the denominator is covered.</p></article>';
    return;
  }
  els.uncoveredItems.innerHTML = items
    .map(
      (item) => `
        <article class="item-card">
          <div class="gap-heading">
            <h3><code>${escapeHtml(item.name)}</code></h3>
            <span class="tag ${escapeHtml(item.kind)}">${escapeHtml(item.kind.replace("_", " "))}</span>
          </div>
          <p>${escapeHtml(item.description)}</p>
          <p><strong>Reason:</strong> ${escapeHtml(item.reason)}</p>
          <p><strong>Focus:</strong> ${escapeHtml(item.generation?.focus || "No generation focus supplied.")}</p>
        </article>
      `,
    )
    .join("");
}

function setInputCollapsed(collapsed) {
  inputCollapsed = collapsed;
  els.input.hidden = collapsed;
  els.toggleInput.textContent = collapsed ? "Show JSON" : "Hide JSON";
  els.toggleInput.setAttribute("aria-expanded", String(!collapsed));
}

function renderReport(report, { collapseInput = false } = {}) {
  const overall = report.coverage?.overall || { item_count: 0, covered_count: 0, uncovered_count: 0 };
  const coverage = coverageLabel(overall);
  const gaps = actionableTools(report);
  els.dashboard.hidden = false;
  els.message.className = "message";
  els.message.hidden = true;
  if (collapseInput) {
    setInputCollapsed(true);
  }
  els.agent.textContent = report.audit?.agent || "unknown";
  els.percent.textContent = coverage.percent;
  els.coverageDetail.textContent = coverage.detail;
  els.actionableCount.textContent = gaps.length;
  els.measuredKinds.textContent = `measured: ${(report.measured_kinds || []).join(", ") || "none"}`;
  renderKindBars(report);
  renderActionableGaps(gaps);
  renderUncoveredItems(report);
}

function renderError(message) {
  els.dashboard.hidden = true;
  els.message.hidden = false;
  els.message.className = "message error";
  els.message.textContent = message;
  setInputCollapsed(false);
}

function renderFromInput(options = {}) {
  const text = els.input.value.trim();
  if (!text) {
    els.dashboard.hidden = true;
    els.message.hidden = false;
    els.message.className = "message";
    els.message.textContent = `Paste or open a ${REPORT_SCHEMA} JSON report.`;
    setInputCollapsed(false);
    return;
  }
  try {
    renderReport(parseReport(text), options);
  } catch (error) {
    renderError(error instanceof Error ? error.message : "Could not parse report.");
  }
}

els.input.addEventListener("input", renderFromInput);
els.toggleInput.addEventListener("click", () => {
  setInputCollapsed(!inputCollapsed);
});
els.sample.addEventListener("click", () => {
  els.input.value = JSON.stringify(sampleReport, null, 2);
  renderFromInput({ collapseInput: true });
});
els.file.addEventListener("change", async () => {
  const [file] = els.file.files;
  if (!file) {
    return;
  }
  els.input.value = await file.text();
  renderFromInput({ collapseInput: true });
});
renderFromInput();
