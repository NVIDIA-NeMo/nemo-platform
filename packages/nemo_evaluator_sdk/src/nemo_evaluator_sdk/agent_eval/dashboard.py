# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Self-contained HTML dashboard for standalone agent-eval runs."""

from __future__ import annotations

import html
import json
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalRunResult,
    AgentEvalTaskResult,
    EvidenceLocator,
    ScoreDeduction,
)


def write_dashboard(result: AgentEvalRunResult, output_path: str | Path) -> Path:
    """Render and write the dashboard HTML."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(result), encoding="utf-8")
    return path


def render_dashboard(result: AgentEvalRunResult) -> str:
    """Return a self-contained HTML report."""
    data_json = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    overall = _format_score(result.summary.overall_score)
    top_deductions = sorted(
        (
            (task_result, deduction)
            for task_result in result.results
            for deduction in task_result.deductions
        ),
        key=lambda item: item[1].normalized_impact,
        reverse=True,
    )[:25]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_e(result.run_id)} Agent Eval Report</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#15171a; --muted:#667085; --line:#d0d5dd; --panel:#fff; --accent:#0f766e; --bad:#b42318; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111418; --fg:#f3f4f6; --muted:#a4aebc; --line:#30363d; --panel:#1b2027; --accent:#5eead4; --bad:#ff8a80; }} }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--fg); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    header {{ padding:28px 32px 20px; border-bottom:1px solid var(--line); background:var(--panel); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:18px; letter-spacing:0; }}
    main {{ max-width:1280px; margin:0 auto; padding:24px 32px 48px; }}
    .hero {{ display:flex; gap:24px; align-items:flex-end; flex-wrap:wrap; }}
    .score {{ font-size:54px; font-weight:700; line-height:1; color:var(--accent); }}
    .muted {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .card strong {{ display:block; font-size:22px; margin-top:6px; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th, td {{ padding:9px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ font-size:12px; text-transform:uppercase; color:var(--muted); }}
    tr:last-child td {{ border-bottom:0; }}
    .deduction {{ color:var(--bad); font-weight:600; }}
    .toolbar {{ display:flex; gap:8px; margin:16px 0; flex-wrap:wrap; }}
    input, select, button {{ border:1px solid var(--line); border-radius:6px; padding:8px 10px; background:var(--panel); color:var(--fg); }}
    button {{ cursor:pointer; }}
    details {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; margin:10px 0; }}
    summary {{ padding:12px 14px; cursor:pointer; }}
    details table {{ border:0; border-top:1px solid var(--line); }}
    a {{ color:var(--accent); }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); border-radius:999px; padding:2px 8px; color:var(--muted); }}
  </style>
</head>
<body>
<header>
  <div class="hero">
    <div>
      <h1>Agent Eval Report</h1>
      <div class="muted">Run {_e(result.run_id)} · {_e(str(result.summary.task_count))} tasks · {_e(str(result.summary.attempt_count))} attempts</div>
    </div>
    <div class="score">{overall}</div>
  </div>
</header>
<main>
  <section>
    <div class="grid">
      {_cards("Model Scores", result.summary.model_scores)}
      {_cards("Domain Scores", result.summary.domain_scores)}
      {_cards("Criterion Fulfilment", result.summary.criterion_type_fulfilment)}
      <div class="card"><span class="muted">Deductions</span><strong>{result.summary.deduction_count}</strong></div>
    </div>
  </section>
  <section>
    <h2>Top Deductions</h2>
    <div class="toolbar">
      <input id="filter" placeholder="Filter task, model, reason">
      <select id="modelFilter"><option value="">All models</option>{_model_options(result)}</select>
      <button id="exportJson">Export JSON</button>
    </div>
    <table id="deductions">
      <thead><tr><th>Task</th><th>Model</th><th>Lost</th><th>Criterion</th><th>Reason</th><th>Evidence</th></tr></thead>
      <tbody>{_deduction_rows(top_deductions)}</tbody>
    </table>
  </section>
  <section>
    <h2>Task Details</h2>
    {_task_details(result.results)}
  </section>
</main>
<script id="run-data" type="application/json">{html.escape(data_json)}</script>
<script>
const data = JSON.parse(document.getElementById("run-data").textContent);
const filter = document.getElementById("filter");
const modelFilter = document.getElementById("modelFilter");
function applyFilters() {{
  const query = filter.value.toLowerCase();
  const model = modelFilter.value;
  for (const row of document.querySelectorAll("#deductions tbody tr")) {{
    const matchesQuery = !query || row.textContent.toLowerCase().includes(query);
    const matchesModel = !model || row.dataset.model === model;
    row.style.display = matchesQuery && matchesModel ? "" : "none";
  }}
}}
filter.addEventListener("input", applyFilters);
modelFilter.addEventListener("change", applyFilters);
document.getElementById("exportJson").addEventListener("click", () => {{
  const blob = new Blob([JSON.stringify(data, null, 2)], {{type: "application/json"}});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${{data.run_id}}.json`;
  link.click();
  URL.revokeObjectURL(url);
}});
</script>
</body>
</html>
"""


def _cards(title: str, values: dict[str, float]) -> str:
    if not values:
        return f'<div class="card"><span class="muted">{_e(title)}</span><strong>n/a</strong></div>'
    return "".join(
        f'<div class="card"><span class="muted">{_e(title)} · {_e(name)}</span><strong>{_format_score(score)}</strong></div>'
        for name, score in values.items()
    )


def _model_options(result: AgentEvalRunResult) -> str:
    models = sorted({task_result.model_id for task_result in result.results})
    return "".join(f'<option value="{_e(model)}">{_e(model)}</option>' for model in models)


def _deduction_rows(rows: list[tuple[AgentEvalTaskResult, ScoreDeduction]]) -> str:
    rendered = []
    for task_result, deduction in rows:
        rendered.append(
            "<tr "
            f'data-model="{_e(task_result.model_id)}">'
            f"<td>{_e(task_result.task_id)}</td>"
            f"<td>{_e(task_result.model_id)}</td>"
            f'<td class="deduction">{deduction.raw_points:g}</td>'
            f"<td>{_e(deduction.criterion_id)}</td>"
            f"<td>{_e(deduction.reason)}</td>"
            f"<td>{_evidence_links(deduction.evidence)}</td>"
            "</tr>"
        )
    return "".join(rendered)


def _task_details(results: list[AgentEvalTaskResult]) -> str:
    rendered = []
    for result in results:
        rows = "".join(
            "<tr>"
            f"<td>{_e(criterion.criterion_id)}</td>"
            f"<td>{_e(criterion.weight_name)}</td>"
            f"<td>{_e(_criterion_type_label(criterion.criterion_type))}</td>"
            f"<td>{'yes' if criterion.fulfilled else 'no'}</td>"
            f"<td>{_evidence_links(criterion.evidence)}</td>"
            "</tr>"
            for criterion in result.criterion_scores
        )
        rendered.append(
            "<details>"
            f"<summary>{_e(result.task_id)} · {_e(result.model_id)} · {_format_score(result.score)}</summary>"
            "<table><thead><tr><th>Criterion</th><th>Weight</th><th>Type</th><th>Fulfilled</th><th>Evidence</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "</details>"
        )
    return "".join(rendered)


def _evidence_links(locators: list[EvidenceLocator]) -> str:
    if not locators:
        return ""
    return '<div class="chips">' + "".join(_evidence_link(locator) for locator in locators) + "</div>"


def _evidence_link(locator: EvidenceLocator) -> str:
    label = locator.label or locator.kind
    if locator.line is not None:
        label = f"{label}:L{locator.line}"
    if locator.json_path:
        label = f"{label} {locator.json_path}"
    return f'<a class="chip" href="{_e(locator.href())}">{_e(label)}</a>'


def _format_score(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _criterion_type_label(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value or "")


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
