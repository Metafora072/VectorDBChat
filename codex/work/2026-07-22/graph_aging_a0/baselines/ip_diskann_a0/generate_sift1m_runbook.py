#!/usr/bin/env python3
"""Generate the full-scale SIFT1M reversible-cycle IP-DiskANN runbook."""

from pathlib import Path


def replace(stage: int, ids_start: int, ids_end: int) -> list[str]:
    return [
        f"  {stage}:",
        '    operation: "replace"',
        "    tags_start: 0",
        "    tags_end: 10000",
        f"    ids_start: {ids_start}",
        f"    ids_end: {ids_end}",
    ]


def main() -> None:
    lines = [
        "sift-1M-reversible-100:",
        "  max_pts: 1000000",
        "  1:",
        '    operation: "insert"',
        "    start: 0",
        "    end: 1000000",
        "  2:",
        '    operation: "search"',
    ]
    stage = 2
    search_stages = [2]
    for cycle in range(1, 101):
        stage += 1
        lines.extend(replace(stage, 1000000, 1010000))
        stage += 1
        lines.extend(replace(stage, 0, 10000))
        if cycle in {1, 10, 100}:
            stage += 1
            lines.extend([f"  {stage}:", '    operation: "search"'])
            search_stages.append(stage)

    root = Path(__file__).resolve().parent
    (root / "sift1m_cycle_100.yaml").write_text("\n".join(lines) + "\n")
    (root / "sift1m_search_stages.txt").write_text("\n".join(map(str, search_stages)) + "\n")


if __name__ == "__main__":
    main()
