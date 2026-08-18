# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""How much detail training progress is reported with.

One fragment, embedded in every backend's schedule section under one field name,
so the docs, the SDK and Studio can treat the knob uniformly rather than learning
three spellings of it. Deliberately *not* a
:class:`~nmp.customization_common.schema.NamespacedModel`: that base exists to
keep two backends' same-named-but-different models from colliding in the merged
``/apis/customization`` spec, and this is the opposite case -- one model, shared
on purpose, which should emit one component.

Kept in its own module rather than beside the callback that consumes it so the
API layer can import the schema without pulling in the platform SDK that
:mod:`nmp.customization_common.training.progress` needs.
"""

from pydantic import BaseModel, ConfigDict, Field

#: The time-series metrics every backend has in common: the loss family, the
#: learning rate, and the gradient norm. Written as patterns rather than literal
#: names so one entry covers both phases (``train_loss`` and ``val_loss``), the
#: algorithm-specific members of a family (``train_sft_loss``,
#: ``val_preference_loss``), and the dataset-qualified names NeMo-RL produces for
#: a second validation set (``val_heldout_loss``).
DIAGNOSTIC_TIME_SERIES = ("*_loss", "*_lr", "*_grad_norm")

#: Everything, spelled explicitly. This is what a user passes to opt out of a
#: backend's default and record a curve for every metric it emits; leaving the
#: field unset means "the backend's default" instead.
ALL_METRICS = ("*",)

#: Least time between metric reports reaching the Jobs service. Points are always
#: recorded; this only bounds how often the accumulator is sent.
#:
#: Ten seconds is chosen against what it costs and what it buys, both measured: a
#: 594-step run over half an hour drops from 594 requests to 180 and from 36s to
#: 11s blocked inside the training loop, while a progress bar that moves every
#: ten seconds is as live as anyone reads one.
DEFAULT_MIN_REPORT_INTERVAL_SECONDS = 10.0


class ProgressReportingConfig(BaseModel):
    """How much detail training progress is reported to the Jobs service with.

    One knob. Every point the training library logs is recorded and sent -- there
    is no sampling of our own, and the cost of a long run is the Jobs service's
    to solve rather than something to hide behind a cap here (see the payload
    note in :mod:`nmp.customization_common.training.callbacks`).

    What this does express is that a training run produces two kinds
    of metric. A few are worth a *history* -- the loss, the learning rate, the
    gradient norm -- because their shape over time is the whole point. The rest
    are throughput and accounting counters (``tps``, ``mem``, ``num_label_tokens``,
    ``global_valid_toks``) whose *current* value is all anyone reads. Both kinds
    are always reported; only the first kind is accumulated.

    There is no second list for the scalars, and deliberately: the set of metric
    names comes from the training framework at runtime, not from this config, so
    any pair of lists would leave a third category of names in neither. Naming
    the series and letting everything else be a scalar is the only partition that
    stays correct when a framework adds a metric.
    """

    # Every model this is embedded in forbids extras, inheriting it from
    # NamespacedModel, and unsloth's schema module states the contract outright:
    # "typos in the JSON shape become validation errors, not silently-ignored
    # fields". This model is not a NamespacedModel -- deliberately, so it emits
    # one shared OpenAPI component rather than three -- and so it did not inherit
    # that, which made it the one place in the request body where
    # `time_series_metric` was accepted and quietly did nothing.
    model_config = ConfigDict(extra="forbid")

    min_report_interval_seconds: float = Field(
        default=DEFAULT_MIN_REPORT_INTERVAL_SECONDS,
        ge=0.0,
        description=(
            "Least number of seconds between progress reports reaching the Jobs service. Every "
            "metric the training library logs is still recorded at full resolution -- this only "
            "buffers them in memory and decides how often the accumulated set is sent, which is "
            "what the reporting actually costs. 0 sends a report for every step the library logs. "
            "Raising it reduces the time training spends blocked on reporting, at the cost of a "
            "progress bar and charts that update less often."
        ),
    )
    time_series_metrics: list[str] | None = Field(
        default=None,
        description=(
            "Which metrics are recorded as a time series, named exactly as they appear in the "
            "job's status details and so qualified by phase: 'train_loss', 'val_accuracy'. "
            "Glob patterns are accepted, so '*_loss' covers every loss on both phases and '*' "
            "records everything. Omit the field to take the backend's default, which keeps the "
            "loss, learning rate and gradient norm. "
            "Every metric the run produces is reported either way -- one not matched here is "
            "still sent as a current value on every report, it simply has no history, so a "
            "throughput counter like 'train_tps' costs one number rather than several hundred. "
            "The job log names what was matched and what was not."
        ),
    )
