#!/usr/bin/env python3
"""Generate a same-terminal-state IP-DiskANN runbook at cycles 1/10/100."""

from pathlib import Path


def operation(stage: int, kind: str, start: int, end: int) -> list[str]:
    if kind == "replace_out":
        return [
            f"  {stage}:",
            '    operation: "replace"',
            "    tags_start: 0",
            "    tags_end: 2500",
            "    ids_start: 7500",
            "    ids_end: 10000",
        ]
    if kind == "replace_back":
        return [
            f"  {stage}:",
            '    operation: "replace"',
            "    tags_start: 0",
            "    tags_end: 2500",
            "    ids_start: 0",
            "    ids_end: 2500",
        ]
    raise ValueError(kind)


def main() -> None:
    lines = [
        "yfcc-10K-reversible-100:",
        "  max_pts: 7500",
        "  1:",
        '    operation: "insert"',
        "    start: 0",
        "    end: 7500",
        "  2:",
        '    operation: "search"',
    ]
    stage = 2
    checkpoints = {1, 10, 100}
    search_stages = [2]
    for cycle in range(1, 101):
        stage += 1
        lines.extend(operation(stage, "replace_out", 0, 0))
        stage += 1
        lines.extend(operation(stage, "replace_back", 0, 0))
        if cycle in checkpoints:
            stage += 1
            lines.extend([f"  {stage}:", '    operation: "search"'])
            search_stages.append(stage)

    root = Path(__file__).resolve().parent
    (root / "yfcc_cycle_100.yaml").write_text("\n".join(lines) + "\n")
    (root / "search_stages.txt").write_text("\n".join(map(str, search_stages)) + "\n")


if __name__ == "__main__":
    main()
