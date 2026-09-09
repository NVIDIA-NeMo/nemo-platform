# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the OTLP capture both Fabric runtimes share.

The receiver is exercised over real HTTP rather than by calling its methods: it exists because
Relay will only talk to a socket, so the socket is the contract.
"""

from __future__ import annotations

import json
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.otlp_receiver import EXPORT_SUFFIX, READY_FILENAME, OTLPReceiver
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.otlp_writer import (
    OTLP_FILENAME,
    fold_exports,
    otlp_endpoint_fields,
    otlp_trace_path,
    register_trace_evidence,
    traces_dir,
)
from nemo_evaluator_sdk.values.evidence import EVIDENCE_FORMAT_ATIF, EVIDENCE_FORMAT_OTLP, EVIDENCE_TRACE
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from packages.nemo_evaluator_sdk.tests.agent_eval._otlp_testkit import export, post, span_names


@pytest.fixture
def receiver(tmp_path: Path):
    with OTLPReceiver(traces_dir(tmp_path)) as running:
        yield running


def test_an_export_is_stored_and_folds_into_a_readable_trace(receiver, tmp_path: Path) -> None:
    assert post(receiver.endpoint, export("agent run")) == 200

    assert fold_exports(traces_dir(tmp_path)) == 1
    assert span_names(otlp_trace_path(tmp_path)) == ["agent run"]


def test_repeated_flushes_all_survive_the_fold(receiver, tmp_path: Path) -> None:
    # An exporter flushes on its own schedule over a run; a later flush must not lose an earlier one.
    for name in ("first", "second", "third"):
        assert post(receiver.endpoint, export(name)) == 200

    assert fold_exports(traces_dir(tmp_path)) == 3
    assert span_names(otlp_trace_path(tmp_path)) == ["first", "second", "third"]


def test_folding_twice_does_not_double_the_spans(receiver, tmp_path: Path) -> None:
    # A caller that folds again -- a retry, or reprocessed evidence -- must not double what a
    # span-counting metric sees.
    post(receiver.endpoint, export("only"))

    assert fold_exports(traces_dir(tmp_path)) == 1
    assert fold_exports(traces_dir(tmp_path)) == 0
    assert span_names(otlp_trace_path(tmp_path)) == ["only"]


def test_a_folded_export_is_not_kept_alongside_its_own_re_encoding(receiver, tmp_path: Path) -> None:
    post(receiver.endpoint, export("only"))

    fold_exports(traces_dir(tmp_path))

    assert not list(traces_dir(tmp_path).glob(f"*{EXPORT_SUFFIX}"))
    assert otlp_trace_path(tmp_path).is_file()


def test_a_large_export_survives_the_round_trip_whole(receiver, tmp_path: Path) -> None:
    # A real capture ran to 722KB. A line torn across writes parses as neither export, and the
    # reader reports the whole trace malformed rather than the one flush that tore.
    for index in range(4):
        assert post(receiver.endpoint, export(f"span-{index}", padding=150_000)) == 200

    assert fold_exports(traces_dir(tmp_path)) == 4
    lines = otlp_trace_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert all(json.loads(line) for line in lines)


def test_an_export_carrying_no_spans_leaves_no_trace_to_register(receiver, tmp_path: Path) -> None:
    # An exporter may flush an empty batch on shutdown; that is not a trace, and an empty file
    # would be registered as one.
    assert post(receiver.endpoint, ExportTraceServiceRequest().SerializeToString()) == 200

    assert fold_exports(traces_dir(tmp_path)) == 0
    assert not otlp_trace_path(tmp_path).exists()


def test_an_unreadable_export_costs_the_flush_not_the_trace(tmp_path: Path) -> None:
    directory = traces_dir(tmp_path)
    directory.mkdir(parents=True)
    (directory / f"000001{EXPORT_SUFFIX}").write_bytes(b"\xff\xfe not protobuf")
    (directory / f"000002{EXPORT_SUFFIX}").write_bytes(export("survivor"))

    assert fold_exports(directory) == 1
    assert span_names(otlp_trace_path(tmp_path)) == ["survivor"]


def test_a_post_to_another_path_is_refused(receiver) -> None:
    assert post(receiver.endpoint.replace("/v1/traces", "/v1/metrics"), export("agent run")) == 404


def test_a_non_protobuf_body_is_refused_rather_than_guessed_at(receiver, tmp_path: Path) -> None:
    # OTLP/JSON would decode into something plausible and wrong. Relay never sends it.
    assert post(receiver.endpoint, b'{"resourceSpans": []}', media_type="application/json") == 415

    assert fold_exports(traces_dir(tmp_path)) == 0


def test_a_body_that_is_not_an_export_does_not_stop_the_receiver(receiver, tmp_path: Path) -> None:
    # Stored verbatim, so a bad body is only found at fold time -- but the socket must stay up.
    assert post(receiver.endpoint, b"\xff\xfe not protobuf") == 200

    assert post(receiver.endpoint, export("agent run")) == 200
    assert fold_exports(traces_dir(tmp_path)) == 1
    assert span_names(otlp_trace_path(tmp_path)) == ["agent run"]


def test_concurrent_flushes_each_land_as_their_own_export(receiver, tmp_path: Path) -> None:
    names = [f"span-{index}" for index in range(12)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(lambda name: post(receiver.endpoint, export(name)), names))

    assert statuses == [200] * len(names)
    assert fold_exports(traces_dir(tmp_path)) == len(names)
    assert sorted(span_names(otlp_trace_path(tmp_path))) == sorted(names)


def test_the_endpoint_is_loopback_on_a_port_the_os_assigned(receiver) -> None:
    # Port 0 rather than a fixed one: trials run in parallel and would otherwise collide.
    assert receiver.endpoint.startswith("http://127.0.0.1:")
    assert receiver.endpoint.endswith("/v1/traces")
    assert receiver.server_address[1] != 0


def test_leaving_the_context_stops_serving_and_leaves_no_thread(tmp_path: Path) -> None:
    before = threading.active_count()
    with OTLPReceiver(traces_dir(tmp_path)) as running:
        endpoint = running.endpoint
        assert post(endpoint, export("agent run")) == 200

    with pytest.raises(urllib.error.URLError):
        post(endpoint, export("after close"))
    assert threading.active_count() == before


def test_signal_ready_announces_a_bound_socket(tmp_path: Path) -> None:
    # The container runtime waits on this file before starting the harness, so it must mean the
    # socket already accepts exports.
    with OTLPReceiver(traces_dir(tmp_path)) as running:
        running.signal_ready()

        assert (traces_dir(tmp_path) / READY_FILENAME).is_file()
        assert post(running.endpoint, export("agent run")) == 200


def test_the_primary_trace_is_otlp_when_there_is_one_and_atif_otherwise(tmp_path: Path) -> None:
    # ATIF needs no file on disk: Fabric declares it in the artifact manifest and the handle
    # validates it on read.
    atif, otlp = tmp_path / "t.atif.json", tmp_path / OTLP_FILENAME

    atif_only: dict = {}
    register_trace_evidence(atif_only, atif=atif, otlp=otlp)
    assert atif_only[EVIDENCE_TRACE].format == EVIDENCE_FORMAT_ATIF

    otlp.write_text("{}\n", encoding="utf-8")
    both: dict = {}
    register_trace_evidence(both, atif=atif, otlp=otlp)
    assert both[EVIDENCE_TRACE].format == EVIDENCE_FORMAT_OTLP
    # The format decides which view is primary, never which is reachable.
    assert both[f"{EVIDENCE_TRACE}:{EVIDENCE_FORMAT_ATIF}"].format == EVIDENCE_FORMAT_ATIF
    assert both[f"{EVIDENCE_TRACE}:{EVIDENCE_FORMAT_OTLP}"].format == EVIDENCE_FORMAT_OTLP


def test_an_empty_trace_file_is_not_registered(tmp_path: Path) -> None:
    otlp = tmp_path / OTLP_FILENAME
    otlp.touch()

    descriptors: dict = {}
    register_trace_evidence(descriptors, atif=None, otlp=otlp)

    assert descriptors == {}


def test_the_endpoint_fields_are_the_ones_relay_needs() -> None:
    # Shared because both runtimes build this endpoint out of different classes; only the values
    # are common, and a divergence would silently change what Relay exports.
    fields = otlp_endpoint_fields(endpoint="http://127.0.0.1:1/v1/traces", service_name="fabric")

    assert fields == {
        "type": "full",
        "endpoint": "http://127.0.0.1:1/v1/traces",
        "transport": "http_binary",
        "service_name": "fabric",
    }


def test_a_fold_that_dies_partway_leaves_the_previous_trace_intact(receiver, tmp_path: Path, monkeypatch) -> None:
    # Written through a temporary file and moved into place: a half-written trace parses as
    # malformed, and a reader cannot tell it from one the exporter never finished.
    post(receiver.endpoint, export("first"))
    fold_exports(traces_dir(tmp_path))
    post(receiver.endpoint, export("second"))

    def boom(_: bytes) -> str:
        raise RuntimeError("disk full")

    monkeypatch.setattr("nemo_evaluator_sdk.agent_eval.runtimes.fabric.otlp_writer.export_to_json_line", boom)
    with pytest.raises(RuntimeError):
        fold_exports(traces_dir(tmp_path))

    assert span_names(otlp_trace_path(tmp_path)) == ["first"]
    assert not list(traces_dir(tmp_path).glob("*.partial"))
