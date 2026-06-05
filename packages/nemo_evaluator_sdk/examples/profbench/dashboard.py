# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ProfBench-specific dashboard rendering for agent-eval results."""

from __future__ import annotations

import html
import json
from pathlib import Path

from nemo_evaluator_sdk.agent_eval import AgentEvalRunResult, AgentEvalTaskResult
from nemo_evaluator_sdk.agent_eval.dashboard import write_dashboard as write_sdk_dashboard

from .profbench import (
    CriterionType,
    EvidenceLocator,
    ProfBenchRubricDetails,
    ScoreDeduction,
    _criterion_type_labels,
    profbench_details,
)


def write_profbench_dashboard(result: AgentEvalRunResult, output_path: str | Path) -> Path:
    """Write the ProfBench-specific HTML report for an example run."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_profbench_dashboard(result, evidence_base_dir=path.parent), encoding="utf-8")
    return path


def write_example_dashboards(result: AgentEvalRunResult, output_dir: str | Path) -> tuple[Path, Path]:
    """Write generic SDK and ProfBench-specific dashboards for this example."""
    path = Path(output_dir)
    sdk_dashboard_path = write_sdk_dashboard(result, path / "sdk-report.html")
    dashboard_path = write_profbench_dashboard(result, path / "report.html")
    return sdk_dashboard_path, dashboard_path


def render_profbench_dashboard(result: AgentEvalRunResult, *, evidence_base_dir: str | Path | None = None) -> str:
    """Render a ProfBench-aware HTML report from generic agent-eval results."""
    rows = _profbench_result_rows(result.results)
    data_json = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    overall = _format_percent(result.summary.overall_score)
    top_deductions = sorted(
        ((task_result, details, deduction) for task_result, details in rows for deduction in details.deductions),
        key=lambda item: item[2].normalized_impact,
        reverse=True,
    )[:25]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(result.run_id)} ProfBench Report</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#15171a; --muted:#667085; --line:#d0d5dd; --panel:#fff; --accent:#0f766e; --bad:#b42318; --soft:#f8fafc; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111418; --fg:#f3f4f6; --muted:#a4aebc; --line:#30363d; --panel:#1b2027; --accent:#5eead4; --bad:#ff8a80; --soft:#151a21; }} }}
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
    th {{ font-size:12px; text-transform:uppercase; color:var(--muted); background:var(--soft); }}
    tr:last-child td {{ border-bottom:0; }}
    .deduction {{ color:var(--bad); font-weight:600; }}
    .pass {{ color:var(--accent); font-weight:600; }}
    .fail {{ color:var(--bad); font-weight:600; }}
    .toolbar {{ display:flex; gap:8px; margin:16px 0; flex-wrap:wrap; }}
    input, select, button {{ border:1px solid var(--line); border-radius:6px; padding:8px 10px; background:var(--panel); color:var(--fg); }}
    button {{ cursor:pointer; }}
    details {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; margin:10px 0; }}
    summary {{ padding:12px 14px; cursor:pointer; }}
    details table {{ border:0; border-top:1px solid var(--line); }}
    a {{ color:var(--accent); }}
    code {{ background:var(--soft); border-radius:4px; padding:1px 4px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); border-radius:999px; padding:2px 8px; color:var(--muted); text-decoration:none; }}
  </style>
</head>
<body>
<header>
  <div class="hero">
    <div>
      <h1>ProfBench Agent Eval Report</h1>
      <div class="muted">Run {_e(result.run_id)} · {_e(result.summary.task_count)} tasks · {_e(result.summary.attempt_count)} attempts</div>
    </div>
    <div class="score">{overall}</div>
  </div>
</header>
<main>
  <section>
    <div class="grid">
      {_cards("Model Scores", _scores_by_model(rows))}
      {_cards("Domain Scores", _scores_by_domain(rows))}
      {_cards("Criterion Fulfilment", _criterion_fulfilment(rows))}
      <div class="card"><span class="muted">Deductions</span><strong>{_e(_deduction_count(rows))}</strong></div>
    </div>
  </section>
  <section>
    <h2>Highest-Impact Failures</h2>
    <div class="toolbar">
      <input id="filter" placeholder="Filter task, model, reason">
      <select id="modelFilter"><option value="">All models</option>{_model_options(rows)}</select>
      <button id="exportJson">Export JSON</button>
    </div>
    <table id="deductions">
      <thead><tr><th>Task</th><th>Model</th><th>Lost</th><th>Criterion</th><th>Reason</th><th>Evidence</th></tr></thead>
      <tbody>{_deduction_rows(top_deductions, evidence_base_dir=evidence_base_dir)}</tbody>
    </table>
  </section>
  <section>
    <h2>Task Details</h2>
    {_task_details(rows, evidence_base_dir=evidence_base_dir)}
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


def _profbench_result_rows(
    results: list[AgentEvalTaskResult],
) -> list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]:
    rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]] = []
    for task_result in results:
        for output in task_result.outputs:
            details = profbench_details(output)
            if details is not None:
                rows.append((task_result, details))
    return rows


def _cards(title: str, values: dict[str, float]) -> str:
    if not values:
        return f'<div class="card"><span class="muted">{_e(title)}</span><strong>n/a</strong></div>'
    return "".join(
        f'<div class="card"><span class="muted">{_e(title)} · {_e(name)}</span><strong>{_format_percent(score)}</strong></div>'
        for name, score in sorted(values.items())
    )


def _scores_by_model(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for _, details in rows:
        values.setdefault(details.model_id, []).append(details.score)
    return _mean_by_key(values)


def _scores_by_domain(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for _, details in rows:
        values.setdefault(details.domain or "unknown", []).append(details.score)
    return _mean_by_key(values)


def _criterion_fulfilment(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for _, details in rows:
        for criterion in details.criterion_scores:
            for criterion_type in _criterion_type_labels(criterion.criterion_type):
                values.setdefault(criterion_type, []).append(1.0 if criterion.fulfilled else 0.0)
    return _mean_by_key(values)


def _deduction_count(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> int:
    return sum(len(details.deductions) for _, details in rows)


def _model_options(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> str:
    models = sorted({details.model_id for _, details in rows})
    return "".join(f'<option value="{_e(model)}">{_e(model)}</option>' for model in models)


def _deduction_rows(
    rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails, ScoreDeduction]],
    *,
    evidence_base_dir: str | Path | None,
) -> str:
    rendered = []
    for task_result, details, deduction in rows:
        rendered.append(
            "<tr "
            f'data-model="{_e(details.model_id)}">'
            f"<td>{_e(task_result.task_id)}</td>"
            f"<td>{_e(details.model_id)}</td>"
            f'<td class="deduction">{deduction.raw_points:g}</td>'
            f"<td>{_e(deduction.criterion_id)}</td>"
            f"<td>{_e(deduction.reason)}</td>"
            f"<td>{_evidence_links(deduction.evidence, evidence_base_dir=evidence_base_dir)}</td>"
            "</tr>"
        )
    return "".join(rendered)


def _task_details(
    rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]],
    *,
    evidence_base_dir: str | Path | None,
) -> str:
    rendered = []
    for task_result, details in rows:
        criterion_rows = "".join(
            "<tr>"
            f"<td>{_e(criterion.criterion_id)}</td>"
            f"<td>{_e(criterion.weight_name)}</td>"
            f"<td>{_e(_criterion_type_label(criterion.criterion_type))}</td>"
            f"<td>{criterion.points:g}</td>"
            f'<td class="{"pass" if criterion.fulfilled else "fail"}">{"yes" if criterion.fulfilled else "no"}</td>'
            f"<td>{_e(criterion.description)}</td>"
            f"<td>{_e(criterion.metadata.get('score_source', ''))}</td>"
            f"<td>{_e(criterion.judge_reason or '')}</td>"
            f"<td>{_evidence_links(criterion.evidence, evidence_base_dir=evidence_base_dir)}</td>"
            "</tr>"
            for criterion in details.criterion_scores
        )
        rendered.append(
            "<details>"
            f"<summary>{_e(task_result.task_id)} · {_e(details.model_id)} · {_format_percent(details.score)}</summary>"
            "<table><thead><tr><th>Criterion</th><th>Weight</th><th>Type</th><th>Points</th>"
            "<th>Fulfilled</th><th>Description</th><th>Source</th><th>Reason</th><th>Evidence</th></tr></thead>"
            f"<tbody>{criterion_rows}</tbody></table>"
            "</details>"
        )
    return "".join(rendered)


def _evidence_links(locators: list[EvidenceLocator], *, evidence_base_dir: str | Path | None) -> str:
    if not locators:
        return ""
    return (
        '<div class="chips">'
        + "".join(_evidence_link(locator, evidence_base_dir=evidence_base_dir) for locator in locators)
        + "</div>"
    )


def _evidence_link(locator: EvidenceLocator, *, evidence_base_dir: str | Path | None) -> str:
    label = locator.label or locator.kind
    if locator.line is not None:
        label = f"{label}:L{locator.line}"
    if locator.json_path:
        label = f"{label} {locator.json_path}"
    return f'<a class="chip" href="{_e(locator.href(base_dir=evidence_base_dir))}">{_e(label)}</a>'


def _mean_by_key(values: dict[str, list[float]]) -> dict[str, float]:
    return {key: _mean(scores) for key, scores in values.items()}


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _criterion_type_label(value: CriterionType | None) -> str:
    return ", ".join(_criterion_type_labels(value))


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
