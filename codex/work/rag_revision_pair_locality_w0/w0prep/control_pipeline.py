"""Materialize model-specific Control B manifests without outcome metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

import numpy as np

from .common import PreparationGuard, canonical_hash, file_sha256, read_jsonl, write_json
from .controls import SelectedRealPair, UniverseItem, generate_control_b


class Encoder(Protocol):
    def encode(self, sentences: Sequence[str], **kwargs: Any) -> np.ndarray: ...


EncoderFactory = Callable[[dict[str, Any], str], Encoder]


def _default_encoder_factory(config: dict[str, Any], model_key: str) -> Encoder:
    # Keep the heavyweight local-only model import out of fake-encoder tests.
    from .models import load_local_model

    return load_local_model(config, model_key)


def _load_inputs(
    manifest_root: Path,
    source: str,
    *,
    universe_size: int,
    core_size: int,
    reserve_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Path, Path]:
    source_root = manifest_root / source
    pair_path = source_root / "selected_pairs.jsonl"
    universe_path = source_root / "fixed_reference_universe.jsonl"
    if not pair_path.is_file() or not universe_path.is_file():
        raise FileNotFoundError(f"missing frozen workload manifests under {source_root}")
    pairs = read_jsonl(pair_path)
    universe = read_jsonl(universe_path)
    if not pairs:
        raise ValueError(f"{source} selected_pairs.jsonl is empty")
    if len(universe) != universe_size:
        raise ValueError(f"{source} universe must contain exactly {universe_size} rows")

    pair_ids: set[str] = set()
    pair_order: list[tuple[object, ...]] = []
    for row in pairs:
        if row.get("source") != source:
            raise ValueError(f"pair source mismatch in {pair_path}")
        pair_id = row.get("pair_id")
        if not isinstance(pair_id, str) or not pair_id or pair_id in pair_ids:
            raise ValueError(f"invalid or duplicate pair_id in {pair_path}")
        pair_ids.add(pair_id)
        required = (
            "commit_order",
            "document_path",
            "section_path",
            "old_payload_sha256",
            "new_payload_sha256",
            "old_payload",
            "new_payload",
        )
        if any(field not in row for field in required):
            raise ValueError(f"pair {pair_id} is missing a required frozen field")
        pair_order.append(
            (
                int(row["commit_order"]),
                str(row["document_path"]).encode("utf-8"),
                str(row["section_path"]).encode("utf-8"),
                pair_id.encode("utf-8"),
            )
        )
    if pair_order != sorted(pair_order):
        raise ValueError(f"{source} selected pair order is not frozen canonical order")

    universe_ids: set[str] = set()
    for index, row in enumerate(universe):
        if row.get("source") != source:
            raise ValueError(f"universe source mismatch in {universe_path}")
        if row.get("reference_rank") != index:
            raise ValueError(f"{source} universe reference_rank is not contiguous and ordered")
        expected_partition = "core" if index < core_size else "reserve"
        if row.get("partition") != expected_partition:
            raise ValueError(f"{source} universe partition mismatch at rank {index}")
        chunk_id = row.get("canonical_chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in universe_ids:
            raise ValueError(f"invalid or duplicate universe ID at rank {index}")
        universe_ids.add(chunk_id)
        for required in ("document_path", "payload_sha256", "payload"):
            if required not in row:
                raise ValueError(f"universe rank {index} is missing {required}")
    if core_size + reserve_size != universe_size:
        raise ValueError("configured core plus reserve must equal universe size")
    return pairs, universe, pair_path, universe_path


def _normalized_encode(
    encoder: Encoder,
    payloads: Sequence[str],
    *,
    prefix: str,
    dimension: int,
    batch_size: int,
) -> np.ndarray:
    texts = [prefix + payload for payload in payloads]
    raw = encoder.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
    )
    array = np.asarray(raw, dtype=np.float32)
    if array.shape != (len(texts), dimension) or not np.isfinite(array).all():
        raise ValueError("encoder returned an invalid shape or non-finite value")
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if np.any(norms <= np.float32(1e-12)):
        raise ValueError("encoder returned a zero-norm vector")
    normalized = array / norms
    return np.ascontiguousarray(normalized, dtype=np.float32)


def _cache_contract(
    *,
    source: str,
    model: str,
    spec: Mapping[str, Any],
    pair_path: Path,
    universe_path: Path,
    pairs: Sequence[Mapping[str, Any]],
    universe: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "format": "w0-control-b-preparation-embeddings-v1",
        "model": model,
        "model_revision": spec["revision"],
        "prefix": spec["prefix"],
        "dimension": int(spec["dimension"]),
        "source": source,
        "pair_manifest_sha256": file_sha256(pair_path),
        "universe_manifest_sha256": file_sha256(universe_path),
        "pair_order_sha256": canonical_hash(
            [
                [row["pair_id"], row["old_payload_sha256"], row["new_payload_sha256"]]
                for row in pairs
            ]
        ),
        "universe_order_sha256": canonical_hash(
            [[row["reference_rank"], row["canonical_chunk_id"], row["payload_sha256"]] for row in universe]
        ),
    }


def _load_cached_arrays(
    cache_root: Path,
    stem: str,
    contract: Mapping[str, Any],
    *,
    pair_count: int,
    universe_count: int,
    dimension: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    metadata_path = cache_root / f"{stem}.json"
    paths = {
        "universe": cache_root / f"{stem}.universe.npy",
        "old": cache_root / f"{stem}.old.npy",
        "new": cache_root / f"{stem}.new.npy",
    }
    if not metadata_path.is_file() or not all(path.is_file() for path in paths.values()):
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("contract") != dict(contract):
        return None
    if any(metadata.get("files", {}).get(name, {}).get("sha256") != file_sha256(path) for name, path in paths.items()):
        return None
    arrays = {
        name: np.load(path, allow_pickle=False) for name, path in paths.items()
    }
    expected_shapes = {
        "universe": (universe_count, dimension),
        "old": (pair_count, dimension),
        "new": (pair_count, dimension),
    }
    for name, array in arrays.items():
        if array.dtype != np.float32 or array.shape != expected_shapes[name]:
            return None
        if not np.isfinite(array).all() or not np.allclose(
            np.linalg.norm(array, axis=1), 1.0, rtol=1e-5, atol=1e-6
        ):
            return None
    return arrays["universe"], arrays["old"], arrays["new"]


def _write_cached_arrays(
    cache_root: Path,
    stem: str,
    contract: Mapping[str, Any],
    universe: np.ndarray,
    old: np.ndarray,
    new: np.ndarray,
) -> dict[str, Any]:
    cache_root.mkdir(parents=True, exist_ok=True)
    arrays = {"universe": universe, "old": old, "new": new}
    files: dict[str, dict[str, object]] = {}
    for name, array in arrays.items():
        path = cache_root / f"{stem}.{name}.npy"
        np.save(path, np.ascontiguousarray(array, dtype=np.float32), allow_pickle=False)
        files[name] = {
            "path": str(path),
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
            "shape": list(array.shape),
            "dtype": "float32",
        }
    metadata = {"contract": dict(contract), "files": files}
    write_json(cache_root / f"{stem}.json", metadata)
    return metadata


def materialize_control_b(
    config_path: Path,
    *,
    encoder_factory: EncoderFactory | None = None,
    sources: Sequence[str] | None = None,
    models: Sequence[str] = ("minilm", "nomic"),
) -> dict[str, Any]:
    """Encode frozen manifests and write preparation-only Control B artifacts."""

    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["authorization"]["full_measurement"]:
        raise RuntimeError("Control B materialization requires full_measurement=false")
    data_root = Path(config["data_root"])
    guard = PreparationGuard(data_root, config)
    guard.check("control-b:start")
    manifest_root = data_root / "manifests"
    cache_root = data_root / "embeddings" / "preparation"
    fixed = config["fixed_reference"]
    source_names = tuple(sorted(config["sources"])) if sources is None else tuple(sources)
    if not source_names or len(set(source_names)) != len(source_names):
        raise ValueError("sources must be non-empty and unique")
    if any(source not in config["sources"] for source in source_names):
        raise ValueError("unknown source requested")
    if not models or len(set(models)) != len(models):
        raise ValueError("models must be non-empty and unique")
    if any(model not in config["models"] for model in models):
        raise ValueError("unknown model requested")
    factory = _default_encoder_factory if encoder_factory is None else encoder_factory

    inputs: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]], Path, Path]] = {}
    for source in source_names:
        inputs[source] = _load_inputs(
            manifest_root,
            source,
            universe_size=int(fixed["universe_size"]),
            core_size=int(fixed["core_size"]),
            reserve_size=int(fixed["reserve_size"]),
        )

    outputs: dict[str, dict[str, Any]] = {}
    for model in models:
        spec = config["models"][model]
        dimension = int(spec["dimension"])
        encoder: Encoder | None = None
        outputs[model] = {}
        for source in source_names:
            pairs, universe_rows, pair_path, universe_path = inputs[source]
            contract = _cache_contract(
                source=source,
                model=model,
                spec=spec,
                pair_path=pair_path,
                universe_path=universe_path,
                pairs=pairs,
                universe=universe_rows,
            )
            stem = f"{source}.{model}"
            cached = _load_cached_arrays(
                cache_root,
                stem,
                contract,
                pair_count=len(pairs),
                universe_count=len(universe_rows),
                dimension=dimension,
            )
            if cached is None:
                if encoder is None:
                    encoder = factory(config, model)
                universe_embeddings = _normalized_encode(
                    encoder,
                    [str(row["payload"]) for row in universe_rows],
                    prefix=str(spec["prefix"]),
                    dimension=dimension,
                    batch_size=64,
                )
                old_embeddings = _normalized_encode(
                    encoder,
                    [str(row["old_payload"]) for row in pairs],
                    prefix=str(spec["prefix"]),
                    dimension=dimension,
                    batch_size=64,
                )
                new_embeddings = _normalized_encode(
                    encoder,
                    [str(row["new_payload"]) for row in pairs],
                    prefix=str(spec["prefix"]),
                    dimension=dimension,
                    batch_size=64,
                )
                cache_metadata = _write_cached_arrays(
                    cache_root,
                    stem,
                    contract,
                    universe_embeddings,
                    old_embeddings,
                    new_embeddings,
                )
            else:
                universe_embeddings, old_embeddings, new_embeddings = cached
                cache_metadata = json.loads((cache_root / f"{stem}.json").read_text(encoding="utf-8"))

            universe_items = [
                UniverseItem(
                    canonical_chunk_id=str(row["canonical_chunk_id"]),
                    source=source,
                    document_path=str(row["document_path"]),
                    payload_sha256=str(row["payload_sha256"]),
                )
                for row in universe_rows
            ]
            selected = [
                SelectedRealPair(
                    pair_id=str(row["pair_id"]),
                    source=source,
                    document_path=str(row["document_path"]),
                )
                for row in pairs
            ]
            core_ids = [
                str(row["canonical_chunk_id"])
                for row in universe_rows
                if row["partition"] == "core"
            ]
            reserve_ids = [
                str(row["canonical_chunk_id"])
                for row in universe_rows
                if row["partition"] == "reserve"
            ]
            result = generate_control_b(
                model=model,
                selected_pairs=selected,
                old_embeddings=old_embeddings,
                new_embeddings=new_embeddings,
                universe_items=universe_items,
                universe_embeddings=universe_embeddings,
                core_ids_by_source={source: core_ids},
                reserve_ids_by_source={source: reserve_ids},
                expected_dimension=dimension,
                expected_universe_size=int(fixed["universe_size"]),
                expected_core_size=int(fixed["core_size"]),
                expected_reserve_size=int(fixed["reserve_size"]),
            )
            source_root = manifest_root / source
            output_path = source_root / f"control_b_{model}.jsonl"
            result.write_jsonl(output_path)
            complete_pair_ids = {
                str(row["pair_id"]) for row in result.rows if row["status"] == "COMPLETE"
            }
            missing_pair_ids = {
                str(row["pair_id"]) for row in result.rows if row["status"] == "MISSING"
            }
            pair_document = {str(row["pair_id"]): str(row["document_path"]) for row in pairs}
            summary = {
                "artifact_kind": "PREPARATION_ONLY_CONTROL_B",
                "complete_count": result.complete_count,
                "complete_document_count": len({pair_document[item] for item in complete_pair_ids}),
                "control_jsonl_bytes": len(result.jsonl_bytes),
                "control_jsonl_path": str(output_path),
                "control_jsonl_sha256": result.jsonl_sha256,
                "embedding_cache": cache_metadata,
                "fixed_reference": {
                    "core_size": int(fixed["core_size"]),
                    "reserve_size": int(fixed["reserve_size"]),
                    "universe_size": int(fixed["universe_size"]),
                },
                "missing_count": result.missing_count,
                "missing_document_count": len({pair_document[item] for item in missing_pair_ids}),
                "model": model,
                "pair_manifest_path": str(pair_path),
                "pair_manifest_sha256": file_sha256(pair_path),
                "selected_document_count": len(set(pair_document.values())),
                "selected_pair_count": len(pairs),
                "source": source,
                "universe_manifest_path": str(universe_path),
                "universe_manifest_sha256": file_sha256(universe_path),
                "resource": guard.check(f"control-b:{model}:{source}"),
            }
            summary_path = source_root / f"control_b_{model}_summary.json"
            write_json(summary_path, summary)
            outputs[model][source] = {
                "complete_count": result.complete_count,
                "complete_document_count": summary["complete_document_count"],
                "control_jsonl_path": str(output_path),
                "control_jsonl_sha256": result.jsonl_sha256,
                "missing_count": result.missing_count,
                "missing_document_count": summary["missing_document_count"],
                "summary_path": str(summary_path),
                "summary_sha256": file_sha256(summary_path),
            }
    minimum_documents = int(config["sampling"]["min_documents_per_control_per_source"])
    minimum_pairs = int(config["sampling"]["min_pairs_per_control_per_source"])
    failures = {
        f"{model}:{source}": row
        for model, source_rows in outputs.items()
        for source, row in source_rows.items()
        if row["complete_count"] < minimum_pairs
        or row["complete_document_count"] < minimum_documents
    }
    result = {
        "status": "PREPARATION_ONLY_CONTROL_B_MATERIALIZED",
        "config_path": str(config_path),
        "config_sha256": file_sha256(config_path),
        "outputs": outputs,
        "closure_failures": failures,
        "resource": guard.check("control-b:complete"),
    }
    if failures:
        raise RuntimeError(
            "FAIL-W0-WORKLOAD-CLOSURE: Control B minima: "
            + json.dumps(failures, sort_keys=True, separators=(",", ":"))
        )
    return result
