"""Pinned local model materialization and deterministic CPU canaries."""

from __future__ import annotations

import json
import os
from pathlib import Path
import resource
import shutil
import time
from typing import Any

# Transformers resolves this cache location while the module is imported.
# Keep dynamically loaded, hash-pinned Nomic code off the system disk.
_W0_DATA_ROOT = Path(
    "/home/ubuntu/pz/VectorDB/data/VectorDB/rag_revision_pair_locality_w0"
)
os.environ.setdefault("HF_HOME", str(_W0_DATA_ROOT / "hf_runtime"))
os.environ.setdefault("HF_MODULES_CACHE", str(_W0_DATA_ROOT / "hf_runtime" / "modules"))

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from .common import PreparationGuard, canonical_hash, file_sha256, write_json


CANARY_TEXTS = (
    "The API server validates an updated object.",
    "[SECTION] storage > volumes\n\nA persistent volume claim changed.",
    "[SECTION] unicode\n\n邻接版本保持局部语义。",
)


def configure_cpu(threads: int) -> None:
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[key] = str(threads)
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype="<f4")
    import hashlib

    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _verify_artifacts(root: Path, expected: dict[str, str]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, digest in sorted(expected.items()):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        observed[relative] = file_sha256(path)
        if observed[relative] != digest:
            raise RuntimeError(f"artifact hash mismatch: {path}")
    return observed


def prepare_nomic_local_code(data_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    model_dir = data_root / "models" / "nomic-runtime"
    code_dir = data_root / "models" / "nomic-code-runtime"
    original_config = data_root / "models" / "nomic-original" / "config.json"
    if file_sha256(original_config) != spec["config_sha256"]:
        raise RuntimeError("Nomic original config hash mismatch")
    required = (
        code_dir / "configuration_hf_nomic_bert.py",
        code_dir / "modeling_hf_nomic_bert.py",
    )
    expected_code = (
        spec["configuration_code_sha256"],
        spec["modeling_code_sha256"],
    )
    for source, expected in zip(required, expected_code, strict=True):
        if not source.is_file():
            raise FileNotFoundError(source)
        if file_sha256(source) != expected:
            raise RuntimeError(f"Nomic remote-code hash mismatch: {source}")
        shutil.copy2(source, model_dir / source.name)
    config_path = model_dir / "config.json"
    current_hash = file_sha256(config_path)
    if current_hash == spec["config_sha256"]:
        config = json.loads(original_config.read_text(encoding="utf-8"))
        auto_map = config.get("auto_map", {})
        for key, value in list(auto_map.items()):
            auto_map[key] = value.split("--", 1)[-1]
        config["auto_map"] = auto_map
        config["use_flash_attn"] = False
        write_json(config_path, config)
        current_hash = file_sha256(config_path)
    if current_hash != spec["runtime_config_sha256"]:
        raise RuntimeError("Nomic runtime config hash mismatch")
    artifact_hashes = _verify_artifacts(model_dir, spec["artifact_sha256"])
    return {
        "declared_original_config_sha256": spec["config_sha256"],
        "observed_original_config_sha256": file_sha256(original_config),
        "runtime_config_sha256": current_hash,
        "configuration_code_sha256": file_sha256(required[0]),
        "modeling_code_sha256": file_sha256(required[1]),
        "artifact_sha256": artifact_hashes,
    }


def _model_path(model_key: str, data_root: Path) -> Path:
    if model_key == "minilm":
        return Path(
            "/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse/models/"
            "models--sentence-transformers--all-MiniLM-L6-v2/snapshots/"
            "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
        )
    if model_key == "nomic":
        return data_root / "models" / "nomic-runtime"
    raise KeyError(model_key)


def load_local_model(config: dict[str, Any], model_key: str) -> SentenceTransformer:
    data_root = Path(config["data_root"])
    spec = config["models"][model_key]
    if model_key == "nomic":
        prepare_nomic_local_code(data_root, spec)
    model_path = _model_path(model_key, data_root)
    if model_key == "minilm":
        _verify_artifacts(model_path, spec["artifact_sha256"])
    weight_path = model_path / "model.safetensors"
    if file_sha256(weight_path) != spec["weights_sha256"]:
        raise RuntimeError(f"{model_key} weight hash mismatch")
    return SentenceTransformer(
        str(model_path),
        device="cpu",
        trust_remote_code=True,
        local_files_only=True,
        model_kwargs={"attn_implementation": "eager"},
    )


def run_model_canary(
    config: dict[str, Any], model_key: str, output: Path
) -> dict[str, Any]:
    data_root = Path(config["data_root"])
    threads = int(config["resources"]["threads"])
    configure_cpu(threads)
    guard = PreparationGuard(data_root, config)
    guard.check(f"model-canary:{model_key}:start")
    spec = config["models"][model_key]
    local_code: dict[str, Any] | None = None
    if model_key == "nomic":
        local_code = prepare_nomic_local_code(data_root, spec)
    model_path = _model_path(model_key, data_root)
    artifact_hashes = (
        local_code["artifact_sha256"]
        if local_code is not None
        else _verify_artifacts(model_path, spec["artifact_sha256"])
    )
    weight_path = model_path / "model.safetensors"
    if file_sha256(weight_path) != spec["weights_sha256"]:
        raise RuntimeError(f"{model_key} weight hash mismatch")

    prefix = spec["prefix"]
    inputs = [prefix + text for text in CANARY_TEXTS]
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, use_fast=True, local_files_only=True, trust_remote_code=True
    )
    tokenized = tokenizer(inputs, add_special_tokens=True, padding=True)
    token_ids_hash = canonical_hash(tokenized["input_ids"])

    started = time.perf_counter()
    model = load_local_model(config, model_key)
    load_seconds = time.perf_counter() - started
    encode_started = time.perf_counter()
    raw_a = model.encode(
        inputs,
        batch_size=len(inputs),
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
    ).astype(np.float32, copy=False)
    raw_b = model.encode(
        inputs,
        batch_size=len(inputs),
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
    ).astype(np.float32, copy=False)
    if not np.array_equal(raw_a, raw_b):
        raise RuntimeError(f"{model_key} same-process canary is not byte-identical")
    normalized = raw_a / np.maximum(
        np.linalg.norm(raw_a, axis=1, keepdims=True), np.float32(1e-12)
    )
    encode_seconds = time.perf_counter() - encode_started
    result = {
        "model": model_key,
        "repo_id": spec["repo_id"],
        "revision": spec["revision"],
        "prefix": prefix,
        "texts_sha256": canonical_hash(list(CANARY_TEXTS)),
        "token_ids_sha256": token_ids_hash,
        "raw_embedding_sha256": _array_sha256(raw_a),
        "normalized_embedding_sha256": _array_sha256(normalized),
        "shape": list(raw_a.shape),
        "load_seconds": load_seconds,
        "two_encode_seconds": encode_seconds,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "weight_sha256": file_sha256(weight_path),
        "artifact_sha256": artifact_hashes,
        "local_code": local_code,
        "resource": guard.check(f"model-canary:{model_key}:complete"),
    }
    write_json(output, result)
    return result


def compare_model_canaries(
    first_path: Path, second_path: Path, output: Path
) -> dict[str, Any]:
    """Close the fresh-process determinism gate without inspecting outcomes."""
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    if first.get("model") != second.get("model"):
        raise RuntimeError("canary model mismatch")
    fields = (
        "texts_sha256",
        "token_ids_sha256",
        "raw_embedding_sha256",
        "normalized_embedding_sha256",
        "weight_sha256",
        "shape",
    )
    matches = {field: first.get(field) == second.get(field) for field in fields}
    if not all(matches.values()):
        raise RuntimeError(f"fresh-process canary mismatch: {matches}")
    result = {
        "model": first["model"],
        "fresh_process_runs": 2,
        "matches": matches,
        "first_path": str(first_path),
        "second_path": str(second_path),
        "first_sha256": file_sha256(first_path),
        "second_sha256": file_sha256(second_path),
        "peak_rss_bytes": max(first["peak_rss_bytes"], second["peak_rss_bytes"]),
        "status": "PASS-FRESH-PROCESS-DETERMINISM",
    }
    write_json(output, result)
    return result
