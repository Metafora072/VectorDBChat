"""Frozen-source workload and fixed-reference manifest preparation for W0."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Sequence

from transformers import AutoTokenizer

from .alignment import ModifiedPair, align_documents, align_section
from .chunking import Chunk, ChunkingError, canonical_chunk_id, chunk_document
from .common import PreparationGuard, canonical_hash, file_sha256, write_json, write_jsonl


@dataclass(frozen=True)
class RevisionCandidate:
    source: str
    order: int
    parent: str
    child: str
    path: str
    old_oid: str
    new_oid: str


@dataclass(frozen=True)
class RevisionChange:
    """One first-parent tree change, as reported by ``diff-tree --raw``."""

    status: str
    old_mode: str
    new_mode: str
    old_oid: str
    new_oid: str
    old_path: str
    new_path: str


@dataclass(frozen=True)
class HistoryVersion:
    oid: str
    segment: int


@dataclass(frozen=True)
class HistoryIndex:
    versions: dict[str, dict[str, HistoryVersion]]
    segment_audit: tuple[dict[str, Any], ...]


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    # Source repositories are partial clones.  Artifact preparation may need
    # to materialize a pinned historical blob through the host's configured
    # proxy; removing proxy variables here makes that deterministic fetch fail
    # even though the immutable object ID is already frozen in the manifest.
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Lazy blob materialization otherwise invokes repository auto-maintenance
    # after nearly every tiny promisor pack.  Disable only the automatic run;
    # the immutable objects themselves and their hashes are unchanged.
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "gc.auto"
    env["GIT_CONFIG_VALUE_0"] = "0"
    return env


def _git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.check_output(
        ["git", *args], cwd=repo, env=_git_env(), text=text
    )


def _parse_raw_changes(raw: bytes) -> list[RevisionChange]:
    fields = raw.split(b"\0")
    changes: list[RevisionChange] = []
    index = 0
    while index < len(fields) and fields[index]:
        header = fields[index].decode("ascii")
        index += 1
        parts = header.split()
        if len(parts) != 5 or not parts[0].startswith(":"):
            raise ValueError(f"MALFORMED_DIFF_TREE_HEADER: {header!r}")
        old_mode = parts[0][1:]
        new_mode, old_oid, new_oid, status = parts[1:]
        old_path = fields[index].decode("utf-8", errors="strict")
        index += 1
        if status.startswith(("R", "C")):
            new_path = fields[index].decode("utf-8", errors="strict")
            index += 1
        else:
            new_path = old_path
        changes.append(
            RevisionChange(
                status=status,
                old_mode=old_mode,
                new_mode=new_mode,
                old_oid=old_oid,
                new_oid=new_oid,
                old_path=old_path,
                new_path=new_path,
            )
        )
    return changes


def _parse_log(
    repo: Path, lo: str, hi: str
) -> list[tuple[str, str, list[RevisionChange]]]:
    """Explicitly diff every commit in the frozen first-parent range.

    ``git log --name-status`` does not reliably emit a merge commit's tree
    delta.  Resolve the first parent for every revision and compare the two
    trees directly instead.  Raw output also supplies modes and immutable OIDs,
    so candidate enumeration never needs per-candidate ``ls-tree`` calls.
    """

    lines = str(
        _git(repo, "rev-list", "--first-parent", "--reverse", "--parents", f"{lo}..{hi}")
    ).splitlines()
    commits: list[tuple[str, str, list[RevisionChange]]] = []
    for line in lines:
        fields = line.split()
        child = fields[0]
        if len(fields) < 2:
            raise ValueError(f"FIRST_PARENT_MISSING: {child}")
        parent = fields[1]
        raw = bytes(
            _git(
                repo,
                "diff-tree",
                "--no-commit-id",
                "-r",
                "-M100%",
                "--raw",
                "-z",
                parent,
                child,
                "--",
                text=False,
            )
        )
        commits.append((child, parent, _parse_raw_changes(raw)))
    return commits


def _eligible_paths(change: RevisionChange, pattern: re.Pattern[str]) -> list[str]:
    return sorted(
        {
            path
            for path in (change.old_path, change.new_path)
            if pattern.fullmatch(path)
        }
    )


def enumerate_candidates(
    source: str, spec: dict[str, Any], blob_policy: dict[str, Any]
) -> tuple[list[RevisionCandidate], list[dict[str, Any]], dict[str, int]]:
    repo = Path(spec["repo"])
    pattern = re.compile(spec["path_regex"])
    commits = _parse_log(repo, spec["lo"], spec["hi"])
    order_by_commit = {spec["lo"]: -1}
    candidates: list[RevisionCandidate] = []
    audit: list[dict[str, Any]] = []
    for order, (child, parent, records) in enumerate(commits):
        order_by_commit[child] = order
        eligible_records = [record for record in records if _eligible_paths(record, pattern)]
        row: dict[str, Any] = {
            "source": source,
            "order": order,
            "parent": parent,
            "child": child,
            "eligible_record_count": len(eligible_records),
            "eligible_changes": [asdict(record) for record in eligible_records],
        }
        if not parent:
            row["decision"] = "EXCLUDE_ROOT"
        elif len(eligible_records) != 1:
            row["decision"] = "EXCLUDE_NOT_EXACTLY_ONE_ELIGIBLE_PATH"
        else:
            record = eligible_records[0]
            status = record.status
            row["status"] = status
            row["paths"] = [record.old_path, record.new_path]
            if (
                status != "M"
                or record.old_path != record.new_path
                or not pattern.fullmatch(record.new_path)
            ):
                row["decision"] = "EXCLUDE_NON_M_OR_RENAME"
            else:
                path = record.new_path
                row.update(
                    {"path": path, "old_oid": record.old_oid, "new_oid": record.new_oid}
                )
                if (
                    record.old_mode != blob_policy["git_mode"]
                    or record.new_mode != blob_policy["git_mode"]
                ):
                    row["decision"] = "EXCLUDE_GIT_MODE"
                else:
                    row["decision"] = "CANDIDATE"
                    candidates.append(
                        RevisionCandidate(
                            source,
                            order,
                            parent,
                            child,
                            path,
                            record.old_oid,
                            record.new_oid,
                        )
                    )
        audit.append(row)
    return candidates, audit, order_by_commit


class BlobReader:
    def __init__(self, repo: Path, policy: dict[str, Any]):
        self.repo = repo
        self.policy = policy
        self.cache: dict[str, bytes] = {}

    def prefetch(self, oids: Iterable[str]) -> dict[str, int]:
        """Materialize missing promisor blobs in one immutable-object fetch."""
        ordered = sorted(set(oids))
        if ordered:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "fetch.negotiationAlgorithm=noop",
                    "fetch",
                    "origin",
                    "--no-tags",
                    "--no-write-fetch-head",
                    "--recurse-submodules=no",
                    "--filter=blob:none",
                    "--stdin",
                ],
                cwd=self.repo,
                env=_git_env(),
                input="".join(f"{oid}\n" for oid in ordered),
                text=True,
                stdout=subprocess.DEVNULL,
                check=True,
            )
        return {"requested_immutable_oids": len(ordered)}

    def read(self, oid: str) -> bytes:
        if oid not in self.cache:
            raw = bytes(_git(self.repo, "cat-file", "blob", oid, text=False))
            self.cache[oid] = raw
        size = len(self.cache[oid])
        if size < self.policy["min_bytes"]:
            raise ChunkingError("BLOB_TOO_SMALL", str(size))
        if size > self.policy["max_bytes"]:
            raise ChunkingError("BLOB_TOO_LARGE", str(size))
        return self.cache[oid]


def _anchor_json(anchor: Any | None, boundary: str) -> Any:
    return boundary if anchor is None else anchor.identity()


def pair_row(pair: ModifiedPair, *, commit_order: int, tokenizer: Any) -> dict[str, Any]:
    return {
        "pair_id": pair.pair_id,
        "source": pair.source,
        "commit_order": commit_order,
        "parent_commit": pair.parent_commit,
        "child_commit": pair.child_commit,
        "document_path": pair.document_path,
        "section_path": pair.section_path,
        "span_ordinal": pair.span_ordinal,
        "left_anchor": _anchor_json(pair.left_anchor, "__BOF__"),
        "right_anchor": _anchor_json(pair.right_anchor, "__EOF__"),
        "old_document_ordinal": pair.old_chunk.document_ordinal,
        "new_document_ordinal": pair.new_chunk.document_ordinal,
        "old_payload_sha256": pair.old_chunk.payload_sha256,
        "new_payload_sha256": pair.new_chunk.payload_sha256,
        "old_payload": pair.old_chunk.payload,
        "new_payload": pair.new_chunk.payload,
        "old_token_count": len(tokenizer(pair.old_chunk.payload, add_special_tokens=False)["input_ids"]),
        "new_token_count": len(tokenizer(pair.new_chunk.payload, add_special_tokens=False)["input_ids"]),
    }


def _sample_pairs(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    seed = config["seed"]
    limits = config["sampling"]
    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ranked = dict(row)
        ranked["selection_key"] = canonical_hash([seed, row["pair_id"]])
        by_document[row["document_path"]].append(ranked)
    kept: dict[str, list[dict[str, Any]]] = {}
    for document, document_rows in by_document.items():
        kept[document] = sorted(
            document_rows, key=lambda row: (row["selection_key"], row["pair_id"])
        )[: limits["max_pairs_per_document"]]
    selected_documents = sorted(
        kept,
        key=lambda document: (
            min(row["selection_key"] for row in kept[document]),
            document.encode("utf-8"),
        ),
    )[: limits["max_documents_per_source"]]
    selected = [row for document in selected_documents for row in kept[document]]
    return sorted(
        selected,
        key=lambda row: (
            row["commit_order"],
            row["document_path"],
            row["section_path"],
            row["pair_id"],
        ),
    )


def _section_chunks(chunks: Iterable[Chunk], section: str) -> tuple[Chunk, ...]:
    return tuple(chunk for chunk in chunks if chunk.section_path == section)


def _initial_tree_entries(
    repo: Path, commit: str, pattern: re.Pattern[str], git_mode: str
) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in str(_git(repo, "ls-tree", "-r", commit, "--")).splitlines():
        left, path = line.split("\t", 1)
        mode, kind, oid = left.split()
        if pattern.fullmatch(path) and mode == git_mode and kind == "blob":
            entries[path] = oid
    return entries


def _history_oid_index(
    spec: dict[str, Any],
    policy: dict[str, Any],
    revision_audit: Sequence[dict[str, Any]],
) -> HistoryIndex:
    """Index every eligible content version in the frozen first-parent range.

    This is intentionally independent of main-pair candidate admission.  A
    commit that modifies two eligible documents is excluded from the main-pair
    population, but both document versions remain part of temporal history for
    conservative Control C construction.
    """

    repo = Path(spec["repo"])
    pattern = re.compile(spec["path_regex"])
    versions: dict[str, dict[str, HistoryVersion]] = defaultdict(dict)
    segment_audit: list[dict[str, Any]] = []
    active_segment: dict[str, int] = {}
    last_segment: dict[str, int] = {}

    def start_segment(path: str, commit: str, oid: str, event: str) -> None:
        segment = last_segment.get(path, -1) + 1
        last_segment[path] = segment
        active_segment[path] = segment
        versions[path][commit] = HistoryVersion(oid=oid, segment=segment)
        segment_audit.append(
            {
                "document_path": path,
                "commit": commit,
                "event": event,
                "segment": segment,
                "oid": oid,
            }
        )

    def tombstone(path: str, commit: str, event: str) -> None:
        segment = active_segment.pop(path, None)
        if segment is not None:
            segment_audit.append(
                {
                    "document_path": path,
                    "commit": commit,
                    "event": event,
                    "segment": segment,
                    "oid": None,
                }
            )

    for path, oid in _initial_tree_entries(
        repo, spec["lo"], pattern, policy["git_mode"]
    ).items():
        start_segment(path, spec["lo"], oid, "SEGMENT_START_AT_LO")
    zero_oid = "0" * 40
    for row in revision_audit:
        child = row["child"]
        for raw_change in row["eligible_changes"]:
            change = RevisionChange(**raw_change)
            status = change.status[0]
            old_eligible = bool(pattern.fullmatch(change.old_path))
            new_eligible = bool(pattern.fullmatch(change.new_path))
            new_is_blob = (
                change.new_mode == policy["git_mode"] and change.new_oid != zero_oid
            )

            if status == "D":
                if old_eligible:
                    tombstone(change.old_path, child, "TOMBSTONE_DELETE")
                continue
            if status == "R":
                if old_eligible:
                    tombstone(change.old_path, child, "TOMBSTONE_RENAME_OLD")
                if new_eligible and new_is_blob:
                    start_segment(
                        change.new_path, child, change.new_oid, "SEGMENT_START_RENAME_NEW"
                    )
                continue
            if status == "C":
                if new_eligible and new_is_blob:
                    start_segment(
                        change.new_path, child, change.new_oid, "SEGMENT_START_COPY_NEW"
                    )
                continue
            if status == "A":
                if new_eligible and new_is_blob:
                    # A malformed/replace-style diff must still not bridge two
                    # path-existence lifetimes.
                    tombstone(change.new_path, child, "TOMBSTONE_BEFORE_ADD")
                    start_segment(
                        change.new_path, child, change.new_oid, "SEGMENT_START_ADD"
                    )
                continue

            path = change.new_path
            if not new_eligible or not new_is_blob:
                if old_eligible:
                    tombstone(change.old_path, child, "TOMBSTONE_NON_BLOB_OR_OUT_OF_SCOPE")
                continue
            if path not in active_segment:
                start_segment(path, child, change.new_oid, "SEGMENT_START_IMPLICIT")
            else:
                versions[path][child] = HistoryVersion(
                    oid=change.new_oid, segment=active_segment[path]
                )
                segment_audit.append(
                    {
                        "document_path": path,
                        "commit": child,
                        "event": "CONTENT_VERSION",
                        "segment": active_segment[path],
                        "oid": change.new_oid,
                    }
                )
    return HistoryIndex(
        versions={path: dict(commits) for path, commits in versions.items()},
        segment_audit=tuple(segment_audit),
    )


def _control_c(
    selected: list[dict[str, Any]],
    pair_objects: dict[str, ModifiedPair],
    history: dict[str, dict[str, tuple[Chunk, ...]]],
    order_by_commit: dict[str, int],
    history_segments: dict[str, dict[str, int]],
    history_failures: dict[str, dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    history_failures = history_failures or {}
    controls: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for row in selected:
        real = pair_objects[row["pair_id"]]
        document_history = history.get(real.document_path, {})
        target_chunks = document_history.get(real.child_commit)
        if target_chunks is None:
            failure = history_failures.get(real.document_path, {}).get(real.child_commit)
            missing.append(
                {
                    "real_pair_id": real.pair_id,
                    "source": real.source,
                    "document_path": real.document_path,
                    "reason": "MISSING_TARGET_HISTORY_VERSION",
                    "detail": failure or "target commit was not materialized",
                }
            )
            continue
        target_section = _section_chunks(target_chunks, real.section_path)
        if not target_section:
            missing.append(
                {
                    "real_pair_id": real.pair_id,
                    "source": real.source,
                    "document_path": real.document_path,
                    "reason": "MISSING_TARGET_SECTION_IDENTITY",
                    "section_path": real.section_path,
                }
            )
            continue
        target_segment = history_segments.get(real.document_path, {}).get(
            real.child_commit
        )
        if target_segment is None:
            missing.append(
                {
                    "real_pair_id": real.pair_id,
                    "source": real.source,
                    "document_path": real.document_path,
                    "reason": "MISSING_TARGET_PATH_EXISTENCE_SEGMENT",
                }
            )
            continue
        parent_order = order_by_commit.get(real.parent_commit, row["commit_order"] - 1)
        older = sorted(
            (
                (order_by_commit.get(commit, -10**9), commit, chunks)
                for commit, chunks in document_history.items()
                if order_by_commit.get(commit, -10**9) < parent_order
                and history_segments.get(real.document_path, {}).get(commit)
                == target_segment
            ),
            reverse=True,
        )
        chosen: dict[str, Any] | None = None
        saw_old_section = False
        saw_target_pair = False
        exclusion_reasons: Counter[str] = Counter()
        for _, old_commit, old_chunks in older:
            old_section = _section_chunks(old_chunks, real.section_path)
            if not old_section:
                continue
            saw_old_section = True
            aligned = align_section(
                source=real.source,
                parent_commit=old_commit,
                child_commit=real.child_commit,
                document_path=real.document_path,
                section_path=real.section_path,
                old_chunks=old_section,
                new_chunks=target_section,
            )
            exclusion_reasons.update(item.reason_code for item in aligned.exclusions)
            target_chunk_id = canonical_chunk_id(real.source, real.new_chunk)
            target_matches = [
                candidate
                for candidate in aligned.pairs
                if canonical_chunk_id(real.source, candidate.new_chunk)
                == target_chunk_id
            ]
            saw_target_pair = saw_target_pair or bool(target_matches)
            matches = [
                candidate
                for candidate in target_matches
                if candidate.old_chunk.payload_sha256
                not in {real.old_chunk.payload_sha256, real.new_chunk.payload_sha256}
            ]
            if matches:
                control = sorted(matches, key=lambda item: item.pair_id)[0]
                chosen = {
                    "real_pair_id": real.pair_id,
                    "control_pair_id": control.pair_id,
                    "source": real.source,
                    "document_path": real.document_path,
                    "section_path": real.section_path,
                    "control_commit": old_commit,
                    "target_commit": real.child_commit,
                    "anchor_payload_sha256": control.old_chunk.payload_sha256,
                    "anchor_payload": control.old_chunk.payload,
                    "target_payload_sha256": control.new_chunk.payload_sha256,
                    "target_chunk_id": target_chunk_id,
                    "target_document_ordinal": control.new_chunk.document_ordinal,
                }
                break
        if chosen is None:
            failed_versions = history_failures.get(real.document_path, {})
            older_failures = {
                commit: reason
                for commit, reason in failed_versions.items()
                if order_by_commit.get(commit, -10**9) < parent_order
                and history_segments.get(real.document_path, {}).get(commit)
                == target_segment
            }
            if not older and older_failures:
                reason = "MISSING_ALL_OLDER_VERSIONS_FAILED_CHUNKING"
            elif not older:
                reason = "MISSING_NO_NONADJACENT_VERSION"
            elif not saw_old_section:
                reason = "MISSING_SECTION_IDENTITY_IN_HISTORY"
            elif saw_target_pair:
                reason = "MISSING_DISTINCT_HISTORICAL_ANCHOR"
            else:
                reason = "MISSING_NO_EXACT_LCS_1_TO_1_ALIGNMENT"
            missing.append(
                {
                    "real_pair_id": real.pair_id,
                    "source": real.source,
                    "document_path": real.document_path,
                    "reason": reason,
                    "alignment_exclusion_reasons": dict(sorted(exclusion_reasons.items())),
                    "history_chunking_failures": dict(sorted(older_failures.items())),
                }
            )
        else:
            controls.append(chosen)
    return controls, missing


def _checkpoint_chunks(
    source: str,
    spec: dict[str, Any],
    policy: dict[str, Any],
    tokenizer: Any,
    reader: BlobReader,
) -> tuple[list[Chunk], list[dict[str, Any]]]:
    repo = Path(spec["repo"])
    pattern = re.compile(spec["path_regex"])
    raw = str(_git(repo, "ls-tree", "-r", spec["hi"], "--"))
    chunks: list[Chunk] = []
    audit: list[dict[str, Any]] = []
    for line in raw.splitlines():
        left, path = line.split("\t", 1)
        mode, kind, oid = left.split()
        if not pattern.fullmatch(path):
            continue
        row: dict[str, Any] = {"source": source, "path": path, "mode": mode, "oid": oid}
        if mode != policy["git_mode"] or kind != "blob":
            row["decision"] = "EXCLUDE_GIT_MODE"
        else:
            try:
                document_chunks = chunk_document(
                    path, reader.read(oid), spec["format"], tokenizer
                )
            except ChunkingError as exc:
                row["decision"] = exc.reason_code
                row["detail"] = exc.detail
            else:
                row["decision"] = "INCLUDE"
                row["chunk_count"] = len(document_chunks)
                chunks.extend(document_chunks)
        audit.append(row)
    return chunks, audit


def _length_stratum(tokens: int) -> str:
    for upper in (64, 128, 192, 254):
        if tokens <= upper:
            return f"le_{upper}"
    raise ValueError(f"payload exceeds token contract: {tokens}")


def _closure_gate(
    config: dict[str, Any],
    *,
    fixed_reference_count: int,
    control_a_counts: dict[str, int],
    control_c_counts: dict[str, int],
) -> dict[str, Any]:
    sampling = config["sampling"]
    expected_reference = config["fixed_reference"]["universe_size"]
    min_documents = sampling["min_documents_per_control_per_source"]
    min_pairs = sampling["min_pairs_per_control_per_source"]
    checks = {
        "fixed_reference_exact_universe": fixed_reference_count == expected_reference,
        "control_a_min_documents": control_a_counts["documents"] >= min_documents,
        "control_a_min_pairs": control_a_counts["pairs"] >= min_pairs,
        "control_c_min_documents": control_c_counts["documents"] >= min_documents,
        "control_c_min_pairs": control_c_counts["pairs"] >= min_pairs,
    }
    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not reasons else "FAIL-W0-WORKLOAD-CLOSURE",
        "checks": checks,
        "failure_reasons": reasons,
        "required": {
            "fixed_reference_universe": expected_reference,
            "minimum_documents_per_control": min_documents,
            "minimum_pairs_per_control": min_pairs,
        },
    }


def prepare_source(
    source: str,
    config: dict[str, Any],
    tokenizer: Any,
    output_root: Path,
    guard: PreparationGuard,
) -> dict[str, Any]:
    spec = config["sources"][source]
    policy = config["blob_policy"]
    repo = Path(spec["repo"])
    reader = BlobReader(repo, policy)
    candidates, revision_audit, order_by_commit = enumerate_candidates(source, spec, policy)
    history_oid_index = _history_oid_index(spec, policy, revision_audit)
    pattern = re.compile(spec["path_regex"])
    checkpoint_oids = []
    for line in str(_git(repo, "ls-tree", "-r", spec["hi"], "--")).splitlines():
        left, path = line.split("\t", 1)
        mode, kind, oid = left.split()
        if pattern.fullmatch(path) and mode == policy["git_mode"] and kind == "blob":
            checkpoint_oids.append(oid)
    prefetch = reader.prefetch(
        [oid for candidate in candidates for oid in (candidate.old_oid, candidate.new_oid)]
        + checkpoint_oids
        + [
            version.oid
            for versions in history_oid_index.versions.values()
            for version in versions.values()
        ]
    )
    all_pair_rows: list[dict[str, Any]] = []
    pair_objects: dict[str, ModifiedPair] = {}
    alignment_exclusions: list[dict[str, Any]] = []
    materialized_candidates: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates):
        row = asdict(candidate)
        try:
            old_chunks = chunk_document(
                candidate.path,
                reader.read(candidate.old_oid),
                spec["format"],
                tokenizer,
            )
            new_chunks = chunk_document(
                candidate.path,
                reader.read(candidate.new_oid),
                spec["format"],
                tokenizer,
            )
        except ChunkingError as exc:
            row.update({"decision": exc.reason_code, "detail": exc.detail})
        else:
            aligned = align_documents(
                source=source,
                parent_commit=candidate.parent,
                child_commit=candidate.child,
                document_path=candidate.path,
                old_chunks=old_chunks,
                new_chunks=new_chunks,
            )
            row.update(
                {
                    "decision": "MATERIALIZED",
                    "old_chunk_count": len(old_chunks),
                    "new_chunk_count": len(new_chunks),
                    "exact_anchor_count": len(aligned.anchors),
                    "modified_pair_count": len(aligned.pairs),
                    "exclusion_count": len(aligned.exclusions),
                }
            )
            for pair in aligned.pairs:
                pair_objects[pair.pair_id] = pair
                all_pair_rows.append(
                    pair_row(pair, commit_order=candidate.order, tokenizer=tokenizer)
                )
            for exclusion in aligned.exclusions:
                alignment_exclusions.append(
                    {
                        "source": source,
                        "parent_commit": candidate.parent,
                        "child_commit": candidate.child,
                        **asdict(exclusion),
                    }
                )
        materialized_candidates.append(row)
        if index and index % 128 == 0:
            guard.check(f"{source}:revision:{index}")

    selected = _sample_pairs(all_pair_rows, config)
    selected_paths = {row["document_path"] for row in selected}
    history: dict[str, dict[str, tuple[Chunk, ...]]] = defaultdict(dict)
    history_failures: dict[str, dict[str, str]] = defaultdict(dict)
    history_segments: dict[str, dict[str, int]] = defaultdict(dict)
    history_materialization_audit: list[dict[str, Any]] = []
    history_count = 0
    for path in sorted(selected_paths):
        for commit, version in sorted(
            history_oid_index.versions.get(path, {}).items(),
            key=lambda item: (order_by_commit.get(item[0], -10**9), item[0]),
        ):
            history_count += 1
            oid = version.oid
            history_segments[path][commit] = version.segment
            history_row = {
                "source": source,
                "document_path": path,
                "commit": commit,
                "commit_order": order_by_commit.get(commit),
                "oid": oid,
                "path_existence_segment": version.segment,
            }
            try:
                chunks = chunk_document(path, reader.read(oid), spec["format"], tokenizer)
            except ChunkingError as exc:
                reason = exc.reason_code + (f": {exc.detail}" if exc.detail else "")
                history_failures[path][commit] = reason
                history_row.update(
                    {"decision": exc.reason_code, "detail": exc.detail}
                )
            else:
                history[path][commit] = chunks
                history_row.update(
                    {"decision": "MATERIALIZED", "chunk_count": len(chunks)}
                )
            history_materialization_audit.append(history_row)
            if history_count % 128 == 0:
                guard.check(f"{source}:history:{history_count}")
    controls_c, missing_c = _control_c(
        selected,
        pair_objects,
        history,
        order_by_commit,
        history_segments,
        history_failures,
    )
    excluded_hashes = {
        row[key]
        for row in selected
        for key in ("old_payload_sha256", "new_payload_sha256")
    }
    excluded_hashes.update(row["anchor_payload_sha256"] for row in controls_c)
    checkpoint_chunks, checkpoint_audit = _checkpoint_chunks(
        source, spec, policy, tokenizer, reader
    )
    ranked_chunks = []
    for chunk in checkpoint_chunks:
        if chunk.payload_sha256 in excluded_hashes:
            continue
        chunk_id = canonical_chunk_id(source, chunk)
        ranked_chunks.append(
            (
                canonical_hash([config["seed"], source, chunk_id, chunk.payload_sha256]),
                chunk_id,
                chunk,
            )
        )
    ranked_chunks.sort(key=lambda item: (item[0], item[1]))
    universe_size = config["fixed_reference"]["universe_size"]
    reference_available_count = len(ranked_chunks)
    # There is no smaller-N workload: an undersized checkpoint emits an empty
    # reference manifest and deterministically fails workload closure.
    universe = ranked_chunks[:universe_size] if len(ranked_chunks) >= universe_size else []
    universe_rows: list[dict[str, Any]] = []
    for rank, (selection_key, chunk_id, chunk) in enumerate(universe):
        universe_rows.append(
            {
                "source": source,
                "reference_rank": rank,
                "partition": "core"
                if rank < config["fixed_reference"]["core_size"]
                else "reserve",
                "selection_key": selection_key,
                "canonical_chunk_id": chunk_id,
                "document_path": chunk.document_path,
                "section_path": chunk.section_path,
                "occurrence": chunk.occurrence,
                "payload_sha256": chunk.payload_sha256,
                "payload": chunk.payload,
                "token_count": len(tokenizer(chunk.payload, add_special_tokens=False)["input_ids"]),
            }
        )

    core = universe_rows[: config["fixed_reference"]["core_size"]]
    multiplicity = Counter(row["payload_sha256"] for row in universe_rows)
    control_a: list[dict[str, Any]] = []
    missing_a: list[dict[str, Any]] = []
    for pair in selected:
        stratum = _length_stratum(pair["old_token_count"])
        candidates_a = [
            row
            for row in core
            if row["document_path"] != pair["document_path"]
            and multiplicity[row["payload_sha256"]] == 1
            and _length_stratum(row["token_count"]) == stratum
        ]
        if not candidates_a:
            missing_a.append(
                {
                    "real_pair_id": pair["pair_id"],
                    "source": source,
                    "reason": "MISSING_RANDOM_CROSS_DOCUMENT_STRATUM",
                }
            )
            continue
        chosen = min(
            candidates_a,
            key=lambda row: (
                canonical_hash([config["seed"], pair["pair_id"], row["canonical_chunk_id"]]),
                row["canonical_chunk_id"],
            ),
        )
        replacement_index = config["fixed_reference"]["core_size"]
        if replacement_index >= len(universe_rows):
            missing_a.append(
                {
                    "real_pair_id": pair["pair_id"],
                    "source": source,
                    "reason": "MISSING_FIXED_REFERENCE_RESERVE_REPLACEMENT",
                }
            )
            continue
        control_a.append(
            {
                "real_pair_id": pair["pair_id"],
                "source": source,
                "length_stratum": stratum,
                "anchor_id": chosen["canonical_chunk_id"],
                "anchor_payload_sha256": chosen["payload_sha256"],
                "reference_replacement_id": universe_rows[replacement_index][
                    "canonical_chunk_id"
                ],
            }
        )

    source_root = output_root / source
    manifests: dict[str, dict[str, Any]] = {}
    outputs = {
        "revision_audit": revision_audit,
        "materialized_candidates": materialized_candidates,
        "alignment_exclusions": sorted(
            alignment_exclusions,
            key=lambda row: (
                row["child_commit"],
                row["document_path"],
                row["section_path"],
                row["span_ordinal"] if row["span_ordinal"] is not None else -1,
            ),
        ),
        "all_strict_pairs": sorted(all_pair_rows, key=lambda row: row["pair_id"]),
        "selected_pairs": selected,
        "history_materialization_audit": history_materialization_audit,
        "history_segment_audit": [
            {"source": source, **row} for row in history_oid_index.segment_audit
        ],
        "control_c": sorted(controls_c, key=lambda row: row["real_pair_id"]),
        "control_c_missing": sorted(missing_c, key=lambda row: row["real_pair_id"]),
        "checkpoint_audit": checkpoint_audit,
        "fixed_reference_universe": universe_rows,
        "control_a": sorted(control_a, key=lambda row: row["real_pair_id"]),
        "control_a_missing": sorted(missing_a, key=lambda row: row["real_pair_id"]),
    }
    for name, rows in outputs.items():
        path = source_root / f"{name}.jsonl"
        count, digest = write_jsonl(path, rows)
        manifests[name] = {"path": str(path), "count": count, "sha256": digest}

    def complete_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        pair_ids = {row["real_pair_id"] for row in rows}
        docs = {
            pair["document_path"] for pair in selected if pair["pair_id"] in pair_ids
        }
        return {"pairs": len(pair_ids), "documents": len(docs)}

    a_counts = complete_counts(control_a)
    c_counts = complete_counts(controls_c)
    closure = _closure_gate(
        config,
        fixed_reference_count=len(universe_rows),
        control_a_counts=a_counts,
        control_c_counts=c_counts,
    )
    summary = {
        "source": source,
        "strict_pair_count": len(all_pair_rows),
        "selected_pair_count": len(selected),
        "selected_document_count": len({row["document_path"] for row in selected}),
        "fixed_reference_universe_count": len(universe_rows),
        "fixed_reference_available_after_exclusions": reference_available_count,
        "control_a_complete": a_counts,
        "control_c_complete": c_counts,
        "control_b_complete": "PENDING_MODEL_SPECIFIC_DISTANCE_MATCH",
        "closure": closure,
        "manifests": manifests,
        "materialized_blob_count": len(reader.cache),
        "prefetch": prefetch,
        "resource": guard.check(f"{source}:complete"),
    }
    write_json(source_root / "summary.json", summary)
    return summary


def prepare_workload(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["authorization"]["full_measurement"]:
        raise RuntimeError("preparation config must keep full_measurement=false")
    data_root = Path(config["data_root"])
    output_root = data_root / "manifests"
    output_root.mkdir(parents=True, exist_ok=True)
    guard = PreparationGuard(data_root, config)
    guard.check("start")
    tokenizer_root = Path(
        "/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse/models/"
        "models--sentence-transformers--all-MiniLM-L6-v2/snapshots/"
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    )
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_root, use_fast=True, local_files_only=True
    )
    summaries: dict[str, dict[str, Any]] = {}
    for source in sorted(config["sources"]):
        summary = prepare_source(source, config, tokenizer, output_root, guard)
        summaries[source] = summary
        if summary["closure"]["status"] != "PASS":
            result = {
                "status": "FAIL-W0-WORKLOAD-CLOSURE",
                "config_path": str(config_path),
                "config_sha256": file_sha256(config_path),
                "sources": summaries,
                "skipped_sources_due_fail_fast": sorted(set(config["sources"]) - set(summaries)),
                "resource": guard.check(f"fail-fast:{source}"),
            }
            write_json(output_root / "workload_summary.json", result)
            raise RuntimeError(
                "FAIL-W0-WORKLOAD-CLOSURE: "
                + json.dumps(
                    {source: summary["closure"]},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
    result = {
        "config_path": str(config_path),
        "config_sha256": file_sha256(config_path),
        "sources": summaries,
        "resource": guard.check("all_sources_complete"),
    }
    write_json(output_root / "workload_summary.json", result)
    failed = {
        source: summary["closure"]
        for source, summary in summaries.items()
        if summary["closure"]["status"] != "PASS"
    }
    if failed:
        raise RuntimeError(
            "FAIL-W0-WORKLOAD-CLOSURE: "
            + json.dumps(failed, sort_keys=True, separators=(",", ":"))
        )
    return result


def seal_existing_source_failure(config_path: Path, source: str) -> dict[str, Any]:
    """Validate and seal a source failure already written before fail-fast."""
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if source not in config["sources"]:
        raise ValueError(f"unknown source: {source}")
    data_root = Path(config["data_root"])
    source_root = data_root / "manifests" / source
    summary_path = source_root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("source") != source:
        raise RuntimeError("source summary identity mismatch")
    if summary.get("closure", {}).get("status") != "FAIL-W0-WORKLOAD-CLOSURE":
        raise RuntimeError("existing source summary is not a workload-closure failure")
    validated: dict[str, dict[str, Any]] = {}
    for name, record in sorted(summary["manifests"].items()):
        path = Path(record["path"])
        if path.parent != source_root or not path.is_file():
            raise RuntimeError(f"manifest path is outside frozen source root: {path}")
        with path.open("rb") as handle:
            count = sum(1 for line in handle if line.strip())
        digest = file_sha256(path)
        if count != record["count"] or digest != record["sha256"]:
            raise RuntimeError(f"manifest seal mismatch: {path}")
        validated[name] = {"count": count, "sha256": digest, "bytes": path.stat().st_size}
    guard = PreparationGuard(data_root, config)
    result = {
        "status": "FAIL-W0-WORKLOAD-CLOSURE",
        "config_path": str(config_path),
        "config_sha256": file_sha256(config_path),
        "failed_source": source,
        "source_summary_path": str(summary_path),
        "source_summary_sha256": file_sha256(summary_path),
        "closure": summary["closure"],
        "validated_manifests": validated,
        "skipped_sources_due_fail_fast": sorted(set(config["sources"]) - {source}),
        "resource": guard.check(f"sealed-failure:{source}"),
    }
    write_json(data_root / "manifests" / "workload_summary.json", result)
    return result
