# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.profile import load_profile
from nemo_experimentalist_plugin.resolve import (
    ResolveError,
    _dataset_cache_target,
    _harbor_download,
    classify_dataset_value,
    normalize_insight_ref,
    parse_local_insights,
    pick_agent_spec,
    profile_storage_flags,
    resolve_dataset,
    resolve_experiment_inputs,
)
from nemo_insights_plugin.contracts.insights import InsightsFileError
from nemo_insights_plugin.contracts.profile import ProfileError


def insight_dict(title: str = "NOTAM staleness", *, insight_id: str = "ins-1") -> dict:
    return {
        "id": insight_id,
        "title": title,
        "description": "agent files plans through stale-NOTAM airspace",
        "agent": "flight-planner",
        "status": "open",
        "trace_refs": ["t1", "t2", "t3"],
    }


def expected_cache_target(
    cache: Path, name: str, version: str | None = None, *, registry_slug: str = "default"
) -> Path:
    name_digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    version_key = "bare" if version is None else f"version-{hashlib.sha256(version.encode('utf-8')).hexdigest()}"
    return cache / "v2" / registry_slug / f"name-{name_digest}" / version_key


def test_platform_id_passes_through(tmp_path: Path) -> None:
    assert normalize_insight_ref("ins-8f3a", None, tmp_path) == "ins-8f3a"


def test_platform_id_rejects_selector(tmp_path: Path) -> None:
    with pytest.raises(ResolveError, match="local multi-insight"):
        normalize_insight_ref("ins-8f3a", "0", tmp_path)


def test_parse_local_insights_delegates_to_shared_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insight_file = tmp_path / "insight.yaml"
    insight_file.write_text("ignored: by-shared-loader\n", encoding="utf-8")
    loader = Mock(return_value={"id": "from-shared-loader"})
    monkeypatch.setattr("nemo_experimentalist_plugin.resolve.load_insights_document", loader)

    assert parse_local_insights(str(insight_file)) == [{"id": "from-shared-loader"}]
    loader.assert_called_once_with(insight_file)


def test_shared_insights_error_is_translated_without_exception_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insight_file = tmp_path / "insight.yaml"
    insight_file.touch()
    loader = Mock(side_effect=InsightsFileError(f"insights file {insight_file} failed shared validation"))
    monkeypatch.setattr("nemo_experimentalist_plugin.resolve.load_insights_document", loader)

    with pytest.raises(ResolveError) as exc_info:
        parse_local_insights(str(insight_file))

    assert str(exc_info.value) == f"insights file {insight_file} failed shared validation"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_single_object_file_is_normalized_to_scratch_json(tmp_path: Path) -> None:
    f = tmp_path / "insight.json"
    f.write_text(json.dumps(insight_dict()), encoding="utf-8")
    out = normalize_insight_ref(str(f), None, tmp_path / "scratch")
    assert out != str(f)
    assert json.loads(Path(out).read_text(encoding="utf-8")) == insight_dict()


def test_yaml_authored_single_insight_becomes_json(tmp_path: Path) -> None:
    # The local backend reads insight files with json.loads; a YAML-authored
    # file must be rewritten, not passed through raw.
    f = tmp_path / "insight.yaml"
    f.write_text(yaml.safe_dump(insight_dict()), encoding="utf-8")
    out = normalize_insight_ref(str(f), None, tmp_path / "scratch")
    assert json.loads(Path(out).read_text(encoding="utf-8"))["agent"] == "flight-planner"


def test_non_json_insight_entry_is_rejected_before_selection(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(
        "insights:\n  - {id: good, title: Good}\n  - id: dated\n    title: Dated\n    observed_at: 2026-07-14\n",
        encoding="utf-8",
    )
    with pytest.raises(ResolveError, match="entry 1.*JSON-serializable"):
        normalize_insight_ref(str(f), "0", tmp_path / "scratch")


def test_analyst_list_with_one_insight_normalizes(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(yaml.safe_dump({"insights": [insight_dict()]}), encoding="utf-8")
    out = normalize_insight_ref(str(f), None, tmp_path / "scratch")
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["title"] == "NOTAM staleness"


def test_analyst_list_multi_requires_selector(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(
        yaml.safe_dump({"insights": [insight_dict("A", insight_id="i-a"), insight_dict("B", insight_id="i-b")]}),
        encoding="utf-8",
    )
    with pytest.raises(ResolveError) as exc:
        normalize_insight_ref(str(f), None, tmp_path)
    assert "i-a" in str(exc.value) and "i-b" in str(exc.value)  # error lists candidates
    out = normalize_insight_ref(str(f), "i-b", tmp_path / "scratch")
    assert json.loads(Path(out).read_text(encoding="utf-8"))["title"] == "B"


def test_selector_not_found_is_error(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(yaml.safe_dump({"insights": [insight_dict()]}), encoding="utf-8")
    with pytest.raises(ResolveError, match="no-such"):
        normalize_insight_ref(str(f), "no-such", tmp_path)


def test_duplicate_title_selector_is_ambiguous(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(
        yaml.safe_dump(
            {
                "insights": [
                    insight_dict("same", insight_id="a"),
                    insight_dict("same", insight_id="b"),
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ResolveError, match="ambiguous.*zero-based index"):
        normalize_insight_ref(str(f), "same", tmp_path / "scratch")


def test_numeric_selector_uses_zero_based_index(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(
        yaml.safe_dump(
            {
                "insights": [
                    insight_dict("first", insight_id="a"),
                    insight_dict("second", insight_id="b"),
                ]
            }
        ),
        encoding="utf-8",
    )
    selected = normalize_insight_ref(str(f), "1", tmp_path / "scratch")
    assert json.loads(Path(selected).read_text(encoding="utf-8"))["id"] == "b"


def test_numeric_selector_prefers_exact_id_over_index(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(
        yaml.safe_dump(
            {
                "insights": [
                    insight_dict("numeric id", insight_id="1"),
                    insight_dict("index one", insight_id="other"),
                ]
            }
        ),
        encoding="utf-8",
    )
    selected = normalize_insight_ref(str(f), "1", tmp_path / "scratch")
    assert json.loads(Path(selected).read_text(encoding="utf-8"))["title"] == "numeric id"


def test_duplicate_numeric_id_is_ambiguous_before_index_fallback(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(
        yaml.safe_dump(
            {
                "insights": [
                    insight_dict("first", insight_id="1"),
                    insight_dict("second", insight_id="1"),
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ResolveError, match="ambiguous"):
        normalize_insight_ref(str(f), "1", tmp_path / "scratch")


def test_numeric_selector_checks_bounds(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(yaml.safe_dump({"insights": [insight_dict()]}), encoding="utf-8")
    with pytest.raises(ResolveError, match="index 1.*out of range"):
        normalize_insight_ref(str(f), "1", tmp_path / "scratch")


def test_empty_list_is_error(tmp_path: Path) -> None:
    f = tmp_path / "insights.yaml"
    f.write_text(yaml.safe_dump({"insights": []}), encoding="utf-8")
    with pytest.raises(ResolveError, match="no insights"):
        normalize_insight_ref(str(f), None, tmp_path)


async def test_harbor_download_exports_flat_task_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, Path, bool]] = []
    registries: list[str | None] = []

    class FakeClient:
        async def download_dataset(self, name: str, *, output_dir: Path, export: bool) -> None:
            calls.append((name, output_dir, export))

    class FakeFactory:
        @staticmethod
        def create(*, registry_url: str | None) -> FakeClient:
            registries.append(registry_url)
            return FakeClient()

    monkeypatch.setattr("harbor.registry.client.factory.RegistryClientFactory", FakeFactory)

    await _harbor_download("dataset@1", tmp_path, "https://registry.example/index.json")

    assert calls == [("dataset@1", tmp_path, True)]
    assert registries == ["https://registry.example/index.json"]


async def test_harbor_download_uses_package_client_for_namespaced_dataset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, Path, bool]] = []

    class FakePackageClient:
        async def download_dataset(self, name: str, *, output_dir: Path, export: bool) -> None:
            calls.append((name, output_dir, export))

    monkeypatch.setattr(
        "harbor.registry.client.package.PackageDatasetClient",
        FakePackageClient,
    )

    await _harbor_download(
        "terminal-bench/terminal-bench-2-1@6",
        tmp_path,
        "https://registry.example/index.json",
    )

    assert calls == [("terminal-bench/terminal-bench-2-1@6", tmp_path, True)]


def test_registry_cache_keys_are_injective_and_path_safe(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    refs = [
        "dataset",
        "dataset@",
        "dataset@unversioned",
        "dataset@.",
        "dataset@..",
        "dataset@release/candidate",
        r"dataset@release\candidate",
        "dataset@release%2Fcandidate",
        "dataset@50% ready",
        "dataset@日本語@beta",
    ]

    targets = [_dataset_cache_target(ref, None, cache) for ref in refs]
    dataset_root = expected_cache_target(cache, "dataset").parent

    assert len(set(targets)) == len(refs)
    assert targets[0] == expected_cache_target(cache, "dataset")
    assert targets[1] == expected_cache_target(cache, "dataset", "")
    assert targets[2] == expected_cache_target(cache, "dataset", "unversioned")
    assert targets[3] == expected_cache_target(cache, "dataset", ".")
    assert targets[4] == expected_cache_target(cache, "dataset", "..")
    assert all(target.parent == dataset_root for target in targets)
    assert all(target.name not in {"", ".", ".."} for target in targets)


async def test_case_variant_registry_refs_materialize_distinct_lowercase_targets(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    refs = ["Dataset@release", "dataset@release", "dataset@Release"]

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        output_dir.mkdir(parents=True)
        (output_dir / "ref").write_text(name, encoding="utf-8")

    targets = [Path(await resolve_dataset(ref, tmp_path, cache_dir=cache, download=fake_download)) for ref in refs]

    assert len(set(targets)) == len(refs)
    assert [(target / "ref").read_text(encoding="utf-8") for target in targets] == refs
    for target in targets:
        name_component, version_component = target.relative_to(cache).parts[-2:]
        assert name_component == name_component.lower()
        assert version_component == version_component.lower()


async def test_very_long_registry_version_uses_bounded_target_and_staging_components(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    staging_dirs: list[Path] = []
    ref = f"dataset@{'Version-' * 100}"

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        staging_dirs.append(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "ref").write_text(name, encoding="utf-8")

    target = Path(await resolve_dataset(ref, tmp_path, cache_dir=cache, download=fake_download))

    assert (target / "ref").read_text(encoding="utf-8") == ref
    assert max(len(component.encode()) for component in target.relative_to(cache).parts) < 128
    assert len(staging_dirs) == 1
    assert len(staging_dirs[0].name.encode()) < 128


def test_path_form_resolves_against_profile_dir(tmp_path: Path) -> None:
    (tmp_path / "evals" / "train").mkdir(parents=True)
    out = asyncio.run(resolve_dataset("./evals/train", tmp_path))
    assert out == str((tmp_path / "evals" / "train").resolve())


def test_path_form_missing_is_error(tmp_path: Path) -> None:
    with pytest.raises(ResolveError, match="does not exist"):
        asyncio.run(resolve_dataset("./evals/train", tmp_path))


def test_path_form_file_is_rejected_as_not_a_dataset_directory(tmp_path: Path) -> None:
    dataset_file = tmp_path / "train.jsonl"
    dataset_file.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ResolveError, match="not a directory"):
        asyncio.run(resolve_dataset(str(dataset_file), tmp_path))


def test_registry_ref_uses_cache_when_present(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    target = expected_cache_target(cache, "tau2-bench-live-test", "1.0")
    target.mkdir(parents=True)
    called = False

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        nonlocal called
        called = True

    out = asyncio.run(resolve_dataset("tau2-bench-live-test@1.0", tmp_path, cache_dir=cache, download=fake_download))
    assert out == str(target)
    assert called is False


def test_registry_ref_rejects_cached_file(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    target = expected_cache_target(cache, "tau2-bench-live-test", "1.0")
    target.parent.mkdir(parents=True)
    target.write_text("not a dataset directory", encoding="utf-8")

    with pytest.raises(ResolveError, match="cache target.*not a directory"):
        asyncio.run(resolve_dataset("tau2-bench-live-test@1.0", tmp_path, cache_dir=cache))


def test_registry_ref_downloads_when_absent(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    registry = "https://reg.example/registry.json"
    seen: dict = {}

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        seen.update(name=name, output_dir=output_dir, registry_url=registry_url)
        output_dir.mkdir(parents=True)

    out = asyncio.run(
        resolve_dataset(
            "tau2-bench-live-test@1.0",
            tmp_path,
            registry_url=registry,
            cache_dir=cache,
            download=fake_download,
        )
    )
    assert seen["name"] == "tau2-bench-live-test@1.0"
    assert seen["registry_url"] == registry
    slug = hashlib.sha256(registry.encode()).hexdigest()[:12]
    assert out == str(expected_cache_target(cache, "tau2-bench-live-test", "1.0", registry_slug=slug))


async def test_versioned_cache_ignores_old_unversioned_layout(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    old_target = cache / "default" / "dataset" / "1"
    old_target.mkdir(parents=True)
    (old_target / "payload").write_text("old-layout", encoding="utf-8")
    calls = 0

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        nonlocal calls
        calls += 1
        output_dir.mkdir(parents=True)
        (output_dir / "payload").write_text("new-layout", encoding="utf-8")

    out = await resolve_dataset("dataset@1", tmp_path, cache_dir=cache, download=fake_download)

    assert out == str(expected_cache_target(cache, "dataset", "1"))
    assert (Path(out) / "payload").read_text(encoding="utf-8") == "new-layout"
    assert (old_target / "payload").read_text(encoding="utf-8") == "old-layout"
    assert calls == 1


async def test_concurrent_identical_refs_publish_one_complete_winner(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    staging_dirs: list[Path] = []
    slow_started = asyncio.Event()
    release_slow = asyncio.Event()

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        staging_dirs.append(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "payload").write_text(f"complete-{len(staging_dirs)}", encoding="utf-8")
        if len(staging_dirs) == 1:
            slow_started.set()
            await asyncio.wait_for(release_slow.wait(), timeout=1)

    slow_task = asyncio.create_task(resolve_dataset("dataset@1", tmp_path, cache_dir=cache, download=fake_download))
    await asyncio.wait_for(slow_started.wait(), timeout=1)

    winner = await resolve_dataset("dataset@1", tmp_path, cache_dir=cache, download=fake_download)

    assert not slow_task.done()
    assert staging_dirs[0].is_dir()
    assert (staging_dirs[0] / "payload").read_text(encoding="utf-8") == "complete-1"
    assert (Path(winner) / "payload").read_text(encoding="utf-8") == "complete-2"

    release_slow.set()
    loser = await slow_task

    expected = expected_cache_target(cache, "dataset", "1")
    assert winner == loser == str(expected)
    assert (expected / "payload").read_text(encoding="utf-8") == "complete-2"
    assert len(set(staging_dirs)) == 2
    assert all(not staging.exists() for staging in staging_dirs)


async def test_concurrent_unversioned_and_literal_latest_refs_use_distinct_targets(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    staging_dirs: list[Path] = []
    both_started = asyncio.Event()

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        staging_dirs.append(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "payload").write_text(name, encoding="utf-8")
        if len(staging_dirs) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)

    unversioned, latest = await asyncio.gather(
        resolve_dataset("dataset", tmp_path, cache_dir=cache, download=fake_download),
        resolve_dataset("dataset@latest", tmp_path, cache_dir=cache, download=fake_download),
    )

    assert unversioned == str(expected_cache_target(cache, "dataset"))
    assert latest == str(expected_cache_target(cache, "dataset", "latest"))
    assert (Path(unversioned) / "payload").read_text(encoding="utf-8") == "dataset"
    assert (Path(latest) / "payload").read_text(encoding="utf-8") == "dataset@latest"
    assert len(set(staging_dirs)) == 2
    assert all(not staging.exists() for staging in staging_dirs)


def test_cache_keys_never_collide(tmp_path: Path) -> None:
    # foo@1.0 and a distinct dataset literally named foo-1.0 must not share a
    # cache directory (the old value.replace("@","-") key collided them).
    cache = tmp_path / "cache"

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        output_dir.mkdir(parents=True)
        (output_dir / "which").write_text(name, encoding="utf-8")

    first = asyncio.run(resolve_dataset("foo@1.0", tmp_path, cache_dir=cache, download=fake_download))
    second = asyncio.run(resolve_dataset("foo-1.0", tmp_path, cache_dir=cache, download=fake_download))
    assert first != second
    assert (Path(second) / "which").read_text(encoding="utf-8") == "foo-1.0"


def test_unprefixed_relative_path_is_path_not_registry_ref(tmp_path: Path) -> None:
    # 'data/train' contains a separator: a missing dir is a clean path error,
    # never a registry download of the literal name.
    with pytest.raises(ResolveError, match="does not exist"):
        asyncio.run(resolve_dataset("data/train", tmp_path))


async def test_registry_url_makes_namespaced_value_a_registry_ref(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    registry = "https://registry.example/index.json"
    calls: list[tuple[str, str | None]] = []

    async def fake_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        calls.append((name, registry_url))
        output_dir.mkdir(parents=True)

    out = await resolve_dataset(
        "terminal-bench/terminal-bench-2-1@6",
        tmp_path,
        registry_url=registry,
        cache_dir=cache,
        download=fake_download,
    )

    assert Path(out).is_dir()
    assert calls == [("terminal-bench/terminal-bench-2-1@6", registry)]


def test_registry_url_overrides_implicit_local_match(tmp_path: Path) -> None:
    (tmp_path / "terminal-bench").mkdir()

    assert (
        classify_dataset_value(
            "terminal-bench",
            tmp_path,
            registry_url="https://registry.example/index.json",
        )
        == "ref"
    )


def test_registry_url_does_not_override_explicit_path(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()

    out = asyncio.run(
        resolve_dataset(
            "./data",
            tmp_path,
            registry_url="https://registry.example/index.json",
        )
    )

    assert out == str((tmp_path / "data").resolve())


def test_bare_name_matching_local_dir_is_path(tmp_path: Path) -> None:
    (tmp_path / "mydata").mkdir()
    assert classify_dataset_value("mydata", tmp_path) == "path"


def test_bare_name_without_local_match_is_ref(tmp_path: Path) -> None:
    assert classify_dataset_value("mydata", tmp_path) == "ref"
    assert classify_dataset_value("./mydata", tmp_path) == "path"


def test_dataset_path_unknown_user_expansion_is_clean_error(tmp_path: Path) -> None:
    with pytest.raises(ResolveError, match="could not be resolved"):
        asyncio.run(resolve_dataset("~no-such-user-xyz/data", tmp_path))


def test_download_failure_surfaces(tmp_path: Path) -> None:
    async def failing_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        raise RuntimeError("registry unreachable")

    with pytest.raises(ResolveError, match="registry unreachable"):
        asyncio.run(resolve_dataset("some-ds", tmp_path, cache_dir=tmp_path / "c", download=failing_download))


def test_partial_download_does_not_poison_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    staging_dirs: list[Path] = []

    async def partial_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        staging_dirs.append(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "shard-0.jsonl").write_text("truncated", encoding="utf-8")
        raise RuntimeError("connection reset mid-download")

    with pytest.raises(ResolveError, match="connection reset"):
        asyncio.run(resolve_dataset("some-ds@1.0", tmp_path, cache_dir=cache, download=partial_download))
    target = expected_cache_target(cache, "some-ds", "1.0")
    assert not target.exists()  # no truncated dataset masquerading as a cache hit
    assert not staging_dirs[0].exists()

    async def working_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        staging_dirs.append(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "shard-0.jsonl").write_text("complete", encoding="utf-8")

    out = asyncio.run(resolve_dataset("some-ds@1.0", tmp_path, cache_dir=cache, download=working_download))
    assert out == str(target)
    assert (Path(out) / "shard-0.jsonl").read_text(encoding="utf-8") == "complete"
    assert len(set(staging_dirs)) == 2
    assert all(not staging.exists() for staging in staging_dirs)


async def test_cancelled_download_cleans_unique_staging_directory(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    staging_dirs: list[Path] = []
    download_started = asyncio.Event()
    wait_forever = asyncio.Event()

    async def cancelled_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        staging_dirs.append(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "payload").write_text("partial", encoding="utf-8")
        download_started.set()
        await wait_forever.wait()

    task = asyncio.create_task(resolve_dataset("some-ds@1.0", tmp_path, cache_dir=cache, download=cancelled_download))
    await asyncio.wait_for(download_started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert not staging_dirs[0].exists()

    async def working_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        staging_dirs.append(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "payload").write_text("complete", encoding="utf-8")

    out = await resolve_dataset("some-ds@1.0", tmp_path, cache_dir=cache, download=working_download)

    assert (Path(out) / "payload").read_text(encoding="utf-8") == "complete"
    assert len(set(staging_dirs)) == 2
    assert all(not staging.exists() for staging in staging_dirs)


def test_stale_fixed_partial_file_does_not_interfere(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    target = expected_cache_target(cache, "some-ds", "1.0")
    target.parent.mkdir(parents=True)
    target.with_name(target.name + ".partial").write_text("stray file, not a dir", encoding="utf-8")

    async def working_download(name: str, output_dir: Path, registry_url: str | None) -> None:
        output_dir.mkdir(parents=True)

    out = asyncio.run(resolve_dataset("some-ds@1.0", tmp_path, cache_dir=cache, download=working_download))
    assert out == str(target)
    assert Path(out).is_dir()


def make_profile_tree(tmp_path: Path) -> Path:
    for sub in ("evals/task_template", "evals/train", "evals/val"):
        (tmp_path / sub).mkdir(parents=True)
    (tmp_path / "AGENT-SPEC.md").write_text("# spec", encoding="utf-8")
    (tmp_path / "optimizer.yaml").write_text(
        "agent: flight-planner\n"
        "task_template: ./evals/task_template\n"
        "datasets:\n  train: ./evals/train\n  validation: ./evals/val\n"
        "experiment_config:\n  storage:\n    publish_winner: true\n",
        encoding="utf-8",
    )
    return tmp_path / "optimizer.yaml"


def test_pick_agent_spec_delegates_profile_owned_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = make_profile_tree(tmp_path)
    with profile_path.open("a", encoding="utf-8") as profile_file:
        profile_file.write("agent_spec: ./configured.md\n")
    selected = tmp_path / "selected-by-shared-resolver.md"
    selected.write_text("# selected", encoding="utf-8")
    profile = load_profile(profile_path)
    resolver = Mock(return_value=selected)
    monkeypatch.setattr("nemo_experimentalist_plugin.resolve.resolve_agent_spec_path", resolver)

    assert pick_agent_spec(profile) == str(selected)
    resolver.assert_called_once_with(profile.profile_dir, "./configured.md")


def test_shared_profile_error_is_translated_without_exception_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = load_profile(make_profile_tree(tmp_path))
    resolver = Mock(side_effect=ProfileError("shared profile selection failed"))
    monkeypatch.setattr("nemo_experimentalist_plugin.resolve.resolve_agent_spec_path", resolver)

    with pytest.raises(ResolveError) as exc_info:
        pick_agent_spec(profile)

    assert str(exc_info.value) == "shared profile selection failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_full_resolution_from_profile(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))
    inputs = asyncio.run(resolve_experiment_inputs(profile=profile, scratch_dir=tmp_path / "scratch", insight="ins-1"))
    assert inputs.agent == str(tmp_path.resolve())  # agent_source "." → profile dir
    assert inputs.agent_spec == str((tmp_path / "AGENT-SPEC.md").resolve())  # auto-pick
    assert inputs.train_dataset.uri == str((tmp_path / "evals" / "train").resolve())
    assert inputs.train_dataset.metadata == {"id": "train"}
    assert inputs.task_template.uri == str((tmp_path / "evals" / "task_template").resolve())
    assert inputs.workspace == "default"
    assert inputs.config.storage.publish_winner is True
    assert inputs.insight == "ins-1"


def test_direct_resolution_rejects_insight_id_without_insight(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))
    with pytest.raises(ResolveError, match="--insight-id.*without.*insight"):
        asyncio.run(
            resolve_experiment_inputs(
                profile=profile,
                scratch_dir=tmp_path / "scratch",
                insight=None,
                insight_id="0",
            )
        )


def test_flags_override_profile(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))
    (tmp_path / "other-train").mkdir()
    inputs = asyncio.run(
        resolve_experiment_inputs(
            profile=profile,
            scratch_dir=tmp_path / "s",
            insight="ins-1",
            agent="git@host:g/r.git@main",
            workspace="ws2",
            train_dataset=str(tmp_path / "other-train"),
        )
    )
    assert inputs.agent == "git@host:g/r.git@main"
    assert inputs.workspace == "ws2"
    assert inputs.train_dataset.uri == str(tmp_path / "other-train")


def test_no_profile_missing_inputs_lists_them(tmp_path: Path) -> None:
    with pytest.raises(ResolveError) as exc:
        asyncio.run(resolve_experiment_inputs(profile=None, scratch_dir=tmp_path, insight="ins-1"))
    msg = str(exc.value)
    assert "train-dataset" in msg and "validation-dataset" in msg and "task-template" in msg
    assert "optimizer.yaml" in msg  # error shows the profile skeleton


def test_no_profile_all_flags_works(tmp_path: Path) -> None:
    for sub in ("t", "v", "tt"):
        (tmp_path / sub).mkdir()
    inputs = asyncio.run(
        resolve_experiment_inputs(
            profile=None,
            scratch_dir=tmp_path / "s",
            insight="ins-1",
            agent=str(tmp_path),
            train_dataset=str(tmp_path / "t"),
            validation_dataset=str(tmp_path / "v"),
            task_template=str(tmp_path / "tt"),
        )
    )
    assert inputs.workspace == "default"
    assert inputs.config.model_dump() == EvolutionaryOptimizerConfig().model_dump()


def test_profileless_mode2_requires_effective_agent_source(tmp_path: Path) -> None:
    for sub in ("train", "validation"):
        (tmp_path / sub).mkdir()

    with pytest.raises(ResolveError, match="--agent"):
        asyncio.run(
            resolve_experiment_inputs(
                profile=None,
                scratch_dir=tmp_path / "scratch",
                train_dataset=str(tmp_path / "train"),
                validation_dataset=str(tmp_path / "validation"),
            )
        )


def test_config_flag_beats_profile_inline(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))
    inputs = asyncio.run(
        resolve_experiment_inputs(
            profile=profile,
            scratch_dir=tmp_path / "s",
            insight="ins-1",
            config_payload={"storage": {"publish_winner": False}},
        )
    )
    assert inputs.config.storage.publish_winner is False


def test_config_unknown_top_level_key_is_tolerated(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))
    inputs = asyncio.run(
        resolve_experiment_inputs(
            profile=profile,
            scratch_dir=tmp_path / "s",
            insight="ins-1",
            config_payload={"stroage": {"publish_winner": True}, "max_rounds": 2},
        )
    )
    assert inputs.config.max_rounds == 2
    assert inputs.config.storage.publish_winner is False


@pytest.mark.parametrize(
    "config_payload",
    [
        {"storage": {"publish_winer": True}},
        {"source": {"clone_dept": 1}},
        {"coder": {"max_fix_atempts": 1}},
        {"analyzer": {"rationalizer": {"max_summary_token": 100}}},
        {"goal_config": {"max_dept": 2}},
    ],
    ids=["storage", "source", "coder", "deep-analyzer", "goal-config"],
)
def test_config_unknown_typed_nested_key_is_tolerated(tmp_path: Path, config_payload: dict) -> None:
    profile = load_profile(make_profile_tree(tmp_path))

    inputs = asyncio.run(
        resolve_experiment_inputs(
            profile=profile,
            scratch_dir=tmp_path / "s",
            insight="ins-1",
            config_payload=config_payload,
        )
    )

    assert inputs.config == EvolutionaryOptimizerConfig()


def test_evaluator_payload_remains_intentionally_open(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))

    inputs = asyncio.run(
        resolve_experiment_inputs(
            profile=profile,
            scratch_dir=tmp_path / "s",
            insight="ins-1",
            config_payload={"evaluator": {"plugin_specific_option": {"nested": True}}},
        )
    )

    assert inputs.config.evaluator == {"plugin_specific_option": {"nested": True}}


def test_config_invalid_value_is_wrapped_with_source(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))
    with pytest.raises(ResolveError, match="Invalid experiment config from --config"):
        asyncio.run(
            resolve_experiment_inputs(
                profile=profile,
                scratch_dir=tmp_path / "s",
                insight="ins-1",
                config_payload={"storage": "not-a-mapping"},
            )
        )


def test_empty_experiment_config_file_names_the_file(tmp_path: Path) -> None:
    make_profile_tree(tmp_path)
    (tmp_path / "exp.yaml").write_text("# only comments\n", encoding="utf-8")
    (tmp_path / "optimizer.yaml").write_text(
        "agent: flight-planner\n"
        "task_template: ./evals/task_template\n"
        "datasets:\n  train: ./evals/train\n  validation: ./evals/val\n"
        "experiment_config: ./exp.yaml\n",
        encoding="utf-8",
    )
    profile = load_profile(tmp_path / "optimizer.yaml")
    with pytest.raises(ResolveError, match="must be a YAML mapping"):
        asyncio.run(resolve_experiment_inputs(profile=profile, scratch_dir=tmp_path / "s", insight="ins-1"))


def test_profile_agent_spec_must_be_readable_utf8(tmp_path: Path) -> None:
    profile_path = make_profile_tree(tmp_path)
    spec = tmp_path / "AGENT-SPEC.md"
    spec.write_bytes(b"\xff")
    profile = load_profile(profile_path)

    with pytest.raises(ResolveError, match="Could not read agent_spec"):
        asyncio.run(resolve_experiment_inputs(profile=profile, scratch_dir=tmp_path / "s"))


def test_profile_storage_flags_reads_inline_and_path_forms(tmp_path: Path) -> None:
    profile = load_profile(make_profile_tree(tmp_path))  # inline dict with publish_winner: true
    assert profile_storage_flags(profile) == {"publish_winner": True}

    (tmp_path / "exp.yaml").write_text("storage:\n  archive_candidates: true\n", encoding="utf-8")
    (tmp_path / "optimizer.yaml").write_text(
        "agent: flight-planner\n"
        "task_template: ./evals/task_template\n"
        "datasets:\n  train: ./evals/train\n  validation: ./evals/val\n"
        "experiment_config: ./exp.yaml\n",
        encoding="utf-8",
    )
    path_profile = load_profile(tmp_path / "optimizer.yaml")
    assert profile_storage_flags(path_profile) == {"archive_candidates": True}
