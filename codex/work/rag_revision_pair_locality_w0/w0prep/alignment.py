"""Conservative exact-anchor alignment and modified-pair admission for W0."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
from typing import Iterable, Sequence

from .chunking import Chunk, canonical_json_bytes


BOUNDARY_BOF = "__BOF__"
BOUNDARY_EOF = "__EOF__"

REASON_UNCHANGED_EXACT_ANCHOR = "UNCHANGED_EXACT_ANCHOR"
REASON_DELETION = "DELETION_1_TO_0"
REASON_INSERTION = "INSERTION_0_TO_1"
REASON_MULTI_DELETION = "DELETION_MANY_TO_0"
REASON_MULTI_INSERTION = "INSERTION_0_TO_MANY"
REASON_SPLIT = "SPLIT_1_TO_MANY"
REASON_MERGE = "MERGE_MANY_TO_1"
REASON_AMBIGUOUS = "AMBIGUOUS_MANY_TO_MANY"
REASON_REORDER = "REORDER_EXACT_HASH_CROSSING"
REASON_SECTION_REMOVED = "SECTION_IDENTITY_REMOVED"
REASON_SECTION_ADDED = "SECTION_IDENTITY_ADDED"


@dataclass(frozen=True)
class ExactAnchor:
    old_ordinal: int
    new_ordinal: int
    payload_sha256: str
    old_hash_occurrence: int
    new_hash_occurrence: int

    def identity(self) -> list[object]:
        # Paragraph ordinals are recorded above for audit but deliberately do
        # not define identity.  Occurrence ranks are local to this exact hash,
        # making duplicate anchors deterministic without ordinal pairing.
        return [
            self.payload_sha256,
            self.old_hash_occurrence,
            self.new_hash_occurrence,
        ]


@dataclass(frozen=True)
class ModifiedPair:
    pair_id: str
    source: str
    parent_commit: str
    child_commit: str
    document_path: str
    section_path: str
    span_ordinal: int
    left_anchor: ExactAnchor | None
    right_anchor: ExactAnchor | None
    old_chunk: Chunk
    new_chunk: Chunk


@dataclass(frozen=True)
class Exclusion:
    reason_code: str
    document_path: str
    section_path: str
    span_ordinal: int | None
    old_ordinals: tuple[int, ...]
    new_ordinals: tuple[int, ...]


@dataclass(frozen=True)
class AlignmentResult:
    anchors: tuple[ExactAnchor, ...]
    pairs: tuple[ModifiedPair, ...]
    exclusions: tuple[Exclusion, ...]


@dataclass(frozen=True)
class TemporalSectionVersion:
    commit: str
    chunks: tuple[Chunk, ...]


def stable_lcs_matches(
    old_hashes: Sequence[str], new_hashes: Sequence[str]
) -> tuple[tuple[int, int], ...]:
    """Return the lexicographically smallest index-pair sequence among all LCSs.

    The suffix-length DP fixes the maximum length.  At each reconstruction step
    we choose the smallest feasible ``(old_index, new_index)``.  Equal payloads
    are therefore matched by occurrence without relying on hash-map iteration.
    """

    n, m = len(old_hashes), len(new_hashes)
    lengths = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        row = lengths[i]
        next_row = lengths[i + 1]
        for j in range(m - 1, -1, -1):
            if old_hashes[i] == new_hashes[j]:
                row[j] = 1 + next_row[j + 1]
            else:
                row[j] = max(next_row[j], row[j + 1])

    matches: list[tuple[int, int]] = []
    old_start = new_start = 0
    remaining = lengths[0][0]
    while remaining:
        chosen: tuple[int, int] | None = None
        for i in range(old_start, n):
            if lengths[i][new_start] < remaining:
                continue
            for j in range(new_start, m):
                if (
                    old_hashes[i] == new_hashes[j]
                    and lengths[i][j] == remaining
                    and 1 + lengths[i + 1][j + 1] == remaining
                ):
                    chosen = (i, j)
                    break
            if chosen is not None:
                break
        if chosen is None:  # Defensive: the DP invariant must always find one.
            raise AssertionError("LCS reconstruction invariant failed")
        matches.append(chosen)
        old_start, new_start = chosen[0] + 1, chosen[1] + 1
        remaining -= 1
    return tuple(matches)


def _anchor_identity(anchor: ExactAnchor | None, boundary: str) -> object:
    return anchor.identity() if anchor is not None else boundary


def _pair_id(
    *,
    source: str,
    parent_commit: str,
    child_commit: str,
    document_path: str,
    section_path: str,
    left_anchor: ExactAnchor | None,
    right_anchor: ExactAnchor | None,
    span_ordinal: int,
    old_hash: str,
    new_hash: str,
) -> str:
    value = [
        source,
        parent_commit,
        child_commit,
        document_path,
        section_path,
        _anchor_identity(left_anchor, BOUNDARY_BOF),
        _anchor_identity(right_anchor, BOUNDARY_EOF),
        span_ordinal,
        old_hash,
        new_hash,
    ]
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _exclusion_reason(a: int, b: int) -> str:
    if a == 1 and b == 0:
        return REASON_DELETION
    if a == 0 and b == 1:
        return REASON_INSERTION
    if a > 1 and b == 0:
        return REASON_MULTI_DELETION
    if a == 0 and b > 1:
        return REASON_MULTI_INSERTION
    if a == 1 and b > 1:
        return REASON_SPLIT
    if a > 1 and b == 1:
        return REASON_MERGE
    if a > 1 and b > 1:
        return REASON_AMBIGUOUS
    raise AssertionError(f"no exclusion reason for span {a}->{b}")


def align_section(
    *,
    source: str,
    parent_commit: str,
    child_commit: str,
    document_path: str,
    section_path: str,
    old_chunks: Sequence[Chunk],
    new_chunks: Sequence[Chunk],
) -> AlignmentResult:
    """Align one unchanged section and admit only exact-anchor-bounded 1->1."""

    if any(c.document_path != document_path or c.section_path != section_path for c in old_chunks):
        raise ValueError("old chunk scope does not match section")
    if any(c.document_path != document_path or c.section_path != section_path for c in new_chunks):
        raise ValueError("new chunk scope does not match section")
    old_ordered = sorted(old_chunks, key=lambda c: c.document_ordinal)
    new_ordered = sorted(new_chunks, key=lambda c: c.document_ordinal)
    matches = stable_lcs_matches(
        [c.payload_sha256 for c in old_ordered],
        [c.payload_sha256 for c in new_ordered],
    )
    old_seen: Counter[str] = Counter()
    old_hash_occurrence: list[int] = []
    for chunk in old_ordered:
        old_hash_occurrence.append(old_seen[chunk.payload_sha256])
        old_seen[chunk.payload_sha256] += 1
    new_seen: Counter[str] = Counter()
    new_hash_occurrence: list[int] = []
    for chunk in new_ordered:
        new_hash_occurrence.append(new_seen[chunk.payload_sha256])
        new_seen[chunk.payload_sha256] += 1
    anchors = tuple(
        ExactAnchor(
            i,
            j,
            old_ordered[i].payload_sha256,
            old_hash_occurrence[i],
            new_hash_occurrence[j],
        )
        for i, j in matches
    )

    # If an exact hash survives but crosses the chosen LCS, the edit contains a
    # reorder (or an occurrence-ambiguous equivalent).  Conservatively suppress
    # every modified-pair admission in this section.
    matched_old = {i for i, _ in matches}
    matched_new = {j for _, j in matches}
    unmatched_old = Counter(
        c.payload_sha256 for i, c in enumerate(old_ordered) if i not in matched_old
    )
    unmatched_new = Counter(
        c.payload_sha256 for j, c in enumerate(new_ordered) if j not in matched_new
    )
    crossing = sorted(unmatched_old.keys() & unmatched_new.keys())
    if crossing:
        return AlignmentResult(
            anchors=anchors,
            pairs=(),
            exclusions=(
                Exclusion(
                    reason_code=REASON_REORDER,
                    document_path=document_path,
                    section_path=section_path,
                    span_ordinal=None,
                    old_ordinals=tuple(
                        c.document_ordinal
                        for i, c in enumerate(old_ordered)
                        if i not in matched_old
                    ),
                    new_ordinals=tuple(
                        c.document_ordinal
                        for j, c in enumerate(new_ordered)
                        if j not in matched_new
                    ),
                ),
            ),
        )

    pairs: list[ModifiedPair] = []
    exclusions: list[Exclusion] = []
    boundaries = [(-1, -1), *matches, (len(old_ordered), len(new_ordered))]
    for span_ordinal in range(len(boundaries) - 1):
        left_i, left_j = boundaries[span_ordinal]
        right_i, right_j = boundaries[span_ordinal + 1]
        old_span = old_ordered[left_i + 1 : right_i]
        new_span = new_ordered[left_j + 1 : right_j]
        a, b = len(old_span), len(new_span)
        if a == 0 and b == 0:
            continue
        left_anchor = anchors[span_ordinal - 1] if span_ordinal > 0 else None
        right_anchor = anchors[span_ordinal] if span_ordinal < len(anchors) else None
        if a == 1 and b == 1:
            old_chunk, new_chunk = old_span[0], new_span[0]
            pid = _pair_id(
                source=source,
                parent_commit=parent_commit,
                child_commit=child_commit,
                document_path=document_path,
                section_path=section_path,
                left_anchor=left_anchor,
                right_anchor=right_anchor,
                span_ordinal=span_ordinal,
                old_hash=old_chunk.payload_sha256,
                new_hash=new_chunk.payload_sha256,
            )
            pairs.append(
                ModifiedPair(
                    pair_id=pid,
                    source=source,
                    parent_commit=parent_commit,
                    child_commit=child_commit,
                    document_path=document_path,
                    section_path=section_path,
                    span_ordinal=span_ordinal,
                    left_anchor=left_anchor,
                    right_anchor=right_anchor,
                    old_chunk=old_chunk,
                    new_chunk=new_chunk,
                )
            )
        else:
            exclusions.append(
                Exclusion(
                    reason_code=_exclusion_reason(a, b),
                    document_path=document_path,
                    section_path=section_path,
                    span_ordinal=span_ordinal,
                    old_ordinals=tuple(c.document_ordinal for c in old_span),
                    new_ordinals=tuple(c.document_ordinal for c in new_span),
                )
            )
    return AlignmentResult(anchors, tuple(pairs), tuple(exclusions))


def align_documents(
    *,
    source: str,
    parent_commit: str,
    child_commit: str,
    document_path: str,
    old_chunks: Iterable[Chunk],
    new_chunks: Iterable[Chunk],
) -> AlignmentResult:
    """Align only unchanged section identities and record one-sided sections."""

    old_by_section: defaultdict[str, list[Chunk]] = defaultdict(list)
    new_by_section: defaultdict[str, list[Chunk]] = defaultdict(list)
    for chunk in old_chunks:
        old_by_section[chunk.section_path].append(chunk)
    for chunk in new_chunks:
        new_by_section[chunk.section_path].append(chunk)

    anchors: list[ExactAnchor] = []
    pairs: list[ModifiedPair] = []
    exclusions: list[Exclusion] = []
    for section_path in sorted(old_by_section.keys() | new_by_section.keys()):
        old_section = old_by_section.get(section_path, [])
        new_section = new_by_section.get(section_path, [])
        if not old_section:
            exclusions.append(
                Exclusion(
                    REASON_SECTION_ADDED,
                    document_path,
                    section_path,
                    None,
                    (),
                    tuple(c.document_ordinal for c in new_section),
                )
            )
            continue
        if not new_section:
            exclusions.append(
                Exclusion(
                    REASON_SECTION_REMOVED,
                    document_path,
                    section_path,
                    None,
                    tuple(c.document_ordinal for c in old_section),
                    (),
                )
            )
            continue
        result = align_section(
            source=source,
            parent_commit=parent_commit,
            child_commit=child_commit,
            document_path=document_path,
            section_path=section_path,
            old_chunks=old_section,
            new_chunks=new_section,
        )
        anchors.extend(result.anchors)
        pairs.extend(result.pairs)
        exclusions.extend(result.exclusions)
    return AlignmentResult(tuple(anchors), tuple(pairs), tuple(exclusions))


def collapse_consecutive_versions(
    versions: Sequence[TemporalSectionVersion],
) -> tuple[TemporalSectionVersion, ...]:
    """Collapse consecutive equal states only; an A->B->A rollback stays three."""

    retained: list[TemporalSectionVersion] = []
    previous: tuple[str, ...] | None = None
    for version in versions:
        state = tuple(chunk.payload_sha256 for chunk in version.chunks)
        if state != previous:
            retained.append(version)
            previous = state
    return tuple(retained)


def align_temporal_versions(
    *,
    source: str,
    document_path: str,
    section_path: str,
    old_version: TemporalSectionVersion,
    new_version: TemporalSectionVersion,
) -> AlignmentResult:
    """Control-C entry point; intentionally delegates to the identical rule."""

    return align_section(
        source=source,
        parent_commit=old_version.commit,
        child_commit=new_version.commit,
        document_path=document_path,
        section_path=section_path,
        old_chunks=old_version.chunks,
        new_chunks=new_version.chunks,
    )
