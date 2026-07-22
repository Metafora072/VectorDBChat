#!/usr/bin/env python3
"""Generate an IP-DiskANN runbook that invokes explicit in-place deletion."""

from pathlib import Path


def ranged(stage: int, operation: str, start: int, end: int) -> list[str]:
    return [
        f"  {stage}:",
        f'    operation: "{operation}"',
        f"    start: {start}",
        f"    end: {end}",
    ]


def main() -> None:
    lines = [
        "sift-1M-ipdelete-reversible-100:",
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
        lines.extend(ranged(stage, "delete", 0, 1000))
        stage += 1
        lines.extend(ranged(stage, "insert", 1000000, 1001000))
        stage += 1
        lines.extend(ranged(stage, "delete", 1000000, 1001000))
        stage += 1
        lines.extend(ranged(stage, "insert", 0, 1000))
        if cycle in {1, 10, 100}:
            stage += 1
            lines.extend([f"  {stage}:", '    operation: "search"'])
            search_stages.append(stage)

    root = Path(__file__).resolve().parent
    (root / "sift1m_ipdelete_cycle_100.yaml").write_text("\n".join(lines) + "\n")
    (root / "sift1m_ipdelete_search_stages.txt").write_text("\n".join(map(str, search_stages)) + "\n")


if __name__ == "__main__":
    main()
