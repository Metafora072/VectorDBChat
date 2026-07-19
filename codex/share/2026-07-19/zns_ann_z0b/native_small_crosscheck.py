#!/usr/bin/env python3
"""Build a cycle-positive compact fixture and compare both native engines."""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


INITIAL_HEADER = struct.Struct("<8sIIQQ")
INITIAL = struct.Struct("<QQIHH")
NORMAL_HEADER = struct.Struct("<8sIIQQ")
NORMAL = struct.Struct("<QQQQQQIIHHHH")
LIFE_HEADER = struct.Struct("<8sIIQQ")
LIFE = struct.Struct("<QQQQQHHI")


def write_fixture(root: Path, extra_tail_events: int = 0) -> tuple[Path, Path, Path]:
    run_hash = 0x07192026
    initial = [(1, 0, 4096, 1, 0), (1, 4096, 4096, 1, 0), (1, 8192, 4096, 1, 0)]
    # (seq, request, object, offset, update, batch, fragment, page-index, phase, role, source, reserved)
    events = [
        (1, 1, 1, 0, 1, 1, 4096, 0, 2, 1, 1, 0),
        (2, 2, 2, 0, 2, 1, 4096, 0, 2, 2, 1, 0),
        (2, 2, 2, 4096, 2, 1, 4096, 1, 2, 2, 1, 0),
        (3, 3, 2, 8192, 3, 2, 4096, 0, 2, 2, 1, 0),
        (5, 4, 1, 0, 5, 3, 2048, 0, 2, 1, 1, 0),
        (6, 5, 2, 0, 6, 3, 1024, 0, 2, 2, 1, 0),
    ]
    for index in range(extra_tail_events):
        seq = 7 + index
        # Rewrite one hot page; this keeps the fixture bounded while providing
        # a useful throughput path when --extra-tail-events is large.
        events.append((seq, seq, 2, 0, seq, seq // 128, 4096, 0, 2, 2, 1, 0))
    lifecycle = [(4, 1, 4096, 4, 2, 1, 1, 0)]

    initial_path, normal_path, life_path = root / "initial.bin", root / "normalized.bin", root / "lifecycle.bin"
    with initial_path.open("wb") as out:
        out.write(INITIAL_HEADER.pack(b"Z0BMAP1", 1, INITIAL.size, len(initial), run_hash))
        out.writelines(INITIAL.pack(*row) for row in initial)
    with normal_path.open("wb") as out:
        out.write(NORMAL_HEADER.pack(b"Z0BNORM1", 1, NORMAL.size, len(events), len({row[1] for row in events})))
        out.writelines(NORMAL.pack(*row) for row in events)
    with life_path.open("wb") as out:
        out.write(LIFE_HEADER.pack(b"Z0BLIFE1", 1, LIFE.size, len(lifecycle), run_hash))
        out.writelines(LIFE.pack(*row) for row in lifecycle)
    return initial_path, normal_path, life_path


def write_scale_fixture(root: Path, initial_pages: int, event_count: int) -> tuple[Path, Path, Path]:
    """Stream a high-cardinality scale fixture without a Python row list."""
    if initial_pages <= 0 or event_count <= 0:
        raise ValueError("scale fixture counts must be positive")
    run_hash = 0x07192026
    initial_path, normal_path, life_path = root / "initial.bin", root / "normalized.bin", root / "lifecycle.bin"
    with initial_path.open("wb") as out:
        out.write(INITIAL_HEADER.pack(b"Z0BMAP1", 1, INITIAL.size, initial_pages, run_hash))
        for page in range(initial_pages):
            out.write(INITIAL.pack(1, page * 4096, 4096, 1, 0))
    with normal_path.open("wb") as out:
        out.write(NORMAL_HEADER.pack(b"Z0BNORM1", 1, NORMAL.size, event_count, event_count))
        for index in range(event_count):
            seq = index + 1
            page = (index * 9973) % initial_pages
            out.write(NORMAL.pack(seq, seq, 1, page * 4096, seq, seq // 128,
                                  4096, 0, 2, 1, 1, 0))
    with life_path.open("wb") as out:
        out.write(LIFE_HEADER.pack(b"Z0BLIFE1", 1, LIFE.size, 0, run_hash))
    return initial_path, normal_path, life_path


def common(payload: dict) -> dict:
    cycle_fields = {
        "cycle_index", "start", "last_append_before_gc", "gc_trigger",
        "allocated_new_blocks", "allocated_new_append_bytes", "application_returned_bytes",
        "relocated_pages", "relocation_allocated_bytes", "host_wa_fraction",
        "victim_zone", "relocation_destination", "victim_valid_fraction",
        "free_zones_before_gc", "free_zones_after_reset", "victim_role_pages",
        "update_id_ranges", "batch_id_ranges",
    }
    return {
        "status": payload["status"],
        "sequence_only": payload["sequence_only"],
        "temporal_fields_used": payload["temporal_fields_used"],
        "placement": payload["placement"],
        "random_seed": payload["random_seed"],
        "cleaner": payload["cleaner"],
        "initial_image": payload["initial_image"],
        "bytes": payload["bytes"],
        "host_wa_fraction": payload["host_wa_fraction"],
        "reset_count": payload["reset_count"],
        "complete_cycle_count": payload["complete_cycle_count"],
        "tail": payload["tail"],
        "victim_sequence": payload["victim_sequence"],
        "cycles": [{key: row[key] for key in cycle_fields} for row in payload["cycles"]],
        "final_state_sha256": payload["final_state_sha256"],
        "transition_rolling_sha256": payload["transition_rolling_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--extra-tail-events", type=int, default=0)
    parser.add_argument("--capacity-blocks", type=int, default=3)
    parser.add_argument("--tmp-dir", type=Path)
    parser.add_argument("--benchmark-only", action="store_true")
    parser.add_argument("--benchmark-initial-pages", type=int, default=0)
    parser.add_argument("--benchmark-placement", choices=("canonical", "random", "oracle"), default="canonical")
    args = parser.parse_args()
    placements = [
        ("canonical", 0), ("role", 0),
        ("random", 2026071901), ("random", 2026071902), ("random", 2026071903),
        ("oracle", 0),
    ]
    if args.benchmark_only:
        seed = 2026071901 if args.benchmark_placement == "random" else 0
        placements = [(args.benchmark_placement, seed)]
    with tempfile.TemporaryDirectory(prefix="z0b-native-test-", dir=args.tmp_dir) as tmp:
        root = Path(tmp)
        if args.benchmark_initial_pages:
            initial, normal, life = write_scale_fixture(
                root, args.benchmark_initial_pages, args.extra_tail_events)
            event_count = args.extra_tail_events
        else:
            initial, normal, life = write_fixture(root, args.extra_tail_events)
            event_count = 7 + args.extra_tail_events
        checked = 0
        timings: list[dict] = []
        for placement, seed in placements:
            for cleaner in ("greedy", "oracle"):
                outputs = []
                for executable, suffix in (("z0b_native_replay", "main"), ("z0b_native_reference", "reference")):
                    output = root / f"{placement}-{seed}-{cleaner}-{suffix}.json"
                    command = [
                        str(args.bin_dir / executable),
                        "--initial", str(initial), "--normalized", str(normal),
                        "--lifecycle", str(life), "--capacity-blocks", str(args.capacity_blocks),
                        "--host-spares", "2", "--placement", placement,
                        "--random-seed", str(seed), "--cleaner", cleaner,
                        "--output", str(output),
                    ]
                    completed = subprocess.run(command, check=True, text=True, capture_output=True)
                    timings.append(json.loads(completed.stdout))
                    outputs.append(json.loads(output.read_text()))
                if common(outputs[0]) != common(outputs[1]):
                    raise SystemExit(f"main/reference mismatch: {placement}/{seed}/{cleaner}")
                comparison = root / f"{placement}-{seed}-{cleaner}-comparison.json"
                subprocess.run([
                    sys.executable, str(Path(__file__).with_name("compare_native_results.py")),
                    "--main", str(root / f"{placement}-{seed}-{cleaner}-main.json"),
                    "--reference", str(root / f"{placement}-{seed}-{cleaner}-reference.json"),
                    "--output", str(comparison),
                ], check=True, text=True, capture_output=True)
                if json.loads(comparison.read_text())["primary_equals_reference"] is not True:
                    raise SystemExit("formal exact comparator did not pass")
                if checked == 0 and not args.benchmark_only:
                    # Keep every final/cycle value identical and perturb only
                    # the transition digest.  The formal comparator must still
                    # reject the pair, proving that transient divergence cannot
                    # hide behind a converged final state.
                    altered = dict(outputs[1])
                    altered["transition_rolling_sha256"] = "0" * 64
                    negative_reference = root / "negative-transition-reference.json"
                    negative_reference.write_text(json.dumps(altered))
                    negative = subprocess.run([
                        sys.executable, str(Path(__file__).with_name("compare_native_results.py")),
                        "--main", str(root / f"{placement}-{seed}-{cleaner}-main.json"),
                        "--reference", str(negative_reference),
                        "--output", str(root / "negative-transition-comparison.json"),
                    ], text=True, capture_output=True)
                    if negative.returncode == 0:
                        raise SystemExit("transition-only negative comparison unexpectedly passed")
                if (not args.benchmark_only and
                        (outputs[0]["reset_count"] < 2 or outputs[0]["tail"]["complete_cycle"])):
                    raise SystemExit("fixture failed to exercise complete-cycle/tail semantics")
                checked += 1
        print(json.dumps({
            "status": "pass",
            "configurations_cross_checked": checked,
            "events_per_engine": event_count,
            "max_wall_seconds": max(row["wall_seconds"] for row in timings),
            "max_rss_kib": max(row["max_rss_kib"] for row in timings),
        }, sort_keys=True))


if __name__ == "__main__":
    main()
