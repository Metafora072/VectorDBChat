from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

import numpy as np

from w0prep.common import write_json, write_jsonl
from w0prep.control_pipeline import materialize_control_b


class FakeEncoder:
    def __init__(self, prefix: str, calls: list[list[str]]):
        self.prefix = prefix
        self.calls = calls

    def encode(self, sentences, **_kwargs):
        self.calls.append(list(sentences))
        vectors = {
            "old": [0.8, 0.6],
            "new": [1.0, 0.0],
            "candidate-a": [0.8, 0.6],
            "candidate-z": [0.1, 0.995],
            "same-document": [0.8, 0.6],
            "reserve-1": [0.0, 1.0],
            "reserve-2": [-1.0, 0.0],
        }
        return np.asarray(
            [vectors[text.removeprefix(self.prefix)] for text in sentences], dtype=np.float32
        )


class ControlPipelineTests(unittest.TestCase):
    def _fixture(self, root: Path, *, prefix: str = "") -> Path:
        data_root = root / "data"
        source_root = data_root / "manifests" / "source-a"
        pairs = [
            {
                "pair_id": "pair-1",
                "source": "source-a",
                "commit_order": 1,
                "document_path": "doc/real",
                "section_path": "section",
                "old_payload_sha256": "old-sha",
                "new_payload_sha256": "new-sha",
                "old_payload": "old",
                "new_payload": "new",
            }
        ]
        payloads = ["candidate-z", "candidate-a", "same-document", "reserve-1", "reserve-2"]
        documents = ["doc/z", "doc/a", "doc/real", "reserve/1", "reserve/2"]
        universe = [
            {
                "source": "source-a",
                "reference_rank": index,
                "partition": "core" if index < 3 else "reserve",
                "canonical_chunk_id": f"id-{index}",
                "document_path": documents[index],
                "payload_sha256": f"payload-{index}",
                "payload": payloads[index],
            }
            for index in range(5)
        ]
        write_jsonl(source_root / "selected_pairs.jsonl", pairs)
        write_jsonl(source_root / "fixed_reference_universe.jsonl", universe)
        config = {
            "authorization": {"full_measurement": False},
            "data_root": str(data_root),
            "sources": {"source-a": {}},
            "fixed_reference": {"core_size": 3, "reserve_size": 2, "universe_size": 5},
            "sampling": {
                "min_documents_per_control_per_source": 1,
                "min_pairs_per_control_per_source": 1,
            },
            "resources": {
                "stage_started_unix": time.time(),
                "cpu_ids": ",".join(str(cpu) for cpu in sorted(os.sched_getaffinity(0))),
                "accounted_external_roots": [],
                "hard_storage_bytes": 1 << 40,
                "hard_rss_bytes": 1 << 40,
                "min_mem_available_bytes": 0,
                "min_cgroup_headroom_bytes": 0,
                "hard_wall_seconds": 3600,
            },
            "models": {
                "minilm": {"revision": "rev-minilm", "prefix": prefix, "dimension": 2},
                "nomic": {"revision": "rev-nomic", "prefix": prefix, "dimension": 2},
            },
        }
        config_path = root / "config.json"
        write_json(config_path, config)
        return config_path

    def test_materializes_control_summary_hashes_docs_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = self._fixture(root, prefix="search_document: ")
            calls: list[list[str]] = []

            def factory(_config, _model):
                return FakeEncoder("search_document: ", calls)

            result = materialize_control_b(
                config_path,
                encoder_factory=factory,
                sources=("source-a",),
                models=("nomic",),
            )
            output = result["outputs"]["nomic"]["source-a"]
            self.assertEqual(output["complete_count"], 1)
            self.assertEqual(output["missing_count"], 0)
            self.assertEqual(output["complete_document_count"], 1)
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(text.startswith("search_document: ") for call in calls for text in call))

            rows = [json.loads(line) for line in Path(output["control_jsonl_path"]).read_text().splitlines()]
            self.assertEqual(rows[0]["candidate_id"], "id-1")
            summary_path = Path(output["summary_path"])
            self.assertTrue(summary_path.is_file())
            summary = json.loads(summary_path.read_text())
            self.assertEqual(summary["selected_pair_count"], 1)
            self.assertEqual(summary["fixed_reference"], {"core_size": 3, "reserve_size": 2, "universe_size": 5})
            cache_root = root / "data" / "embeddings" / "preparation"
            self.assertEqual(len(list(cache_root.glob("source-a.nomic.*.npy"))), 3)

    def test_valid_cache_avoids_loading_encoder_and_preserves_control_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = self._fixture(root)
            first = materialize_control_b(
                config_path,
                encoder_factory=lambda _config, _model: FakeEncoder("", []),
                sources=("source-a",),
                models=("minilm",),
            )

            def forbidden_factory(_config, _model):
                raise AssertionError("valid cache must not load a model")

            second = materialize_control_b(
                config_path,
                encoder_factory=forbidden_factory,
                sources=("source-a",),
                models=("minilm",),
            )
            self.assertEqual(
                first["outputs"]["minilm"]["source-a"]["control_jsonl_sha256"],
                second["outputs"]["minilm"]["source-a"]["control_jsonl_sha256"],
            )

    def test_rejects_wrong_pair_source_and_universe_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = self._fixture(root)
            source_root = root / "data" / "manifests" / "source-a"
            pair_path = source_root / "selected_pairs.jsonl"
            pairs = [json.loads(line) for line in pair_path.read_text().splitlines()]
            pairs[0]["source"] = "wrong-source"
            write_jsonl(pair_path, pairs)
            with self.assertRaisesRegex(ValueError, "pair source mismatch"):
                materialize_control_b(
                    config_path,
                    encoder_factory=lambda _config, _model: FakeEncoder("", []),
                    models=("minilm",),
                )

            self._fixture(root)
            universe_path = source_root / "fixed_reference_universe.jsonl"
            universe = [json.loads(line) for line in universe_path.read_text().splitlines()]
            universe[1]["reference_rank"] = 4
            write_jsonl(universe_path, universe)
            with self.assertRaisesRegex(ValueError, "reference_rank"):
                materialize_control_b(
                    config_path,
                    encoder_factory=lambda _config, _model: FakeEncoder("", []),
                    models=("minilm",),
                )


if __name__ == "__main__":
    unittest.main()
