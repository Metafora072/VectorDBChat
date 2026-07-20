from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from w0prep.alignment import (  # noqa: E402
    BOUNDARY_BOF,
    BOUNDARY_EOF,
    REASON_AMBIGUOUS,
    REASON_DELETION,
    REASON_INSERTION,
    REASON_MERGE,
    REASON_MULTI_DELETION,
    REASON_MULTI_INSERTION,
    REASON_REORDER,
    REASON_SECTION_ADDED,
    REASON_SECTION_REMOVED,
    REASON_SPLIT,
    TemporalSectionVersion,
    align_documents,
    align_section,
    collapse_consecutive_versions,
    stable_lcs_matches,
)
from w0prep.chunking import (  # noqa: E402
    Chunk,
    ChunkingError,
    canonical_chunk_id,
    canonical_json_bytes,
    chunk_document,
)


class ScalarTokenizer:
    """One non-whitespace Unicode scalar per token, with exact offsets."""

    def __call__(self, text, *, add_special_tokens, return_offsets_mapping):
        assert add_special_tokens is False
        assert return_offsets_mapping is True
        offsets = [(i, i + 1) for i, char in enumerate(text) if not char.isspace()]
        return {"input_ids": list(range(len(offsets))), "offset_mapping": offsets}


TOK = ScalarTokenizer()


@contextmanager
def raises(exception_type, match):
    try:
        yield
    except exception_type as exc:
        assert re.search(match, str(exc)), str(exc)
    else:
        raise AssertionError(f"expected {exception_type.__name__}")


def chunks(parts, *, section="s", path="doc.md"):
    result = []
    for i, part in enumerate(parts):
        digest = hashlib.sha256(part.encode()).hexdigest()
        result.append(Chunk(path, section, i, i, part, digest))
    return tuple(result)


def align(old, new):
    return align_section(
        source="kubernetes_website",
        parent_commit="1" * 40,
        child_commit="2" * 40,
        document_path="doc.md",
        section_path="s",
        old_chunks=chunks(old),
        new_chunks=chunks(new),
    )


def test_01_prefix_insertion_has_no_cascading_replacements():
    result = align(["A", "B", "C"], ["X", "A", "B", "C"])
    assert not result.pairs
    assert [(a.old_ordinal, a.new_ordinal) for a in result.anchors] == [
        (0, 1), (1, 2), (2, 3)
    ]
    assert [e.reason_code for e in result.exclusions] == [REASON_INSERTION]


def test_02_middle_insertion_preserves_all_exact_anchors():
    result = align(["A", "B", "C"], ["A", "B", "X", "C"])
    assert not result.pairs
    assert [(a.old_ordinal, a.new_ordinal) for a in result.anchors] == [
        (0, 0), (1, 1), (2, 3)
    ]
    assert result.exclusions[0].reason_code == REASON_INSERTION


def test_03_deletion_does_not_shift_later_pairs():
    result = align(["A", "X", "B", "C"], ["A", "B", "C"])
    assert not result.pairs
    assert [(a.old_ordinal, a.new_ordinal) for a in result.anchors] == [
        (0, 0), (2, 1), (3, 2)
    ]
    assert result.exclusions[0].reason_code == REASON_DELETION


def test_04_single_replacement_yields_one_pair_with_bound_identity():
    result = align(["A", "OLD", "C"], ["A", "NEW", "C"])
    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.left_anchor.payload_sha256 == chunks(["A"])[0].payload_sha256
    assert pair.right_anchor.payload_sha256 == chunks(["C"])[0].payload_sha256
    assert pair.span_ordinal == 1
    expected = hashlib.sha256(
        canonical_json_bytes([
            pair.source,
            pair.parent_commit,
            pair.child_commit,
            pair.document_path,
            pair.section_path,
            pair.left_anchor.identity() if pair.left_anchor else BOUNDARY_BOF,
            pair.right_anchor.identity() if pair.right_anchor else BOUNDARY_EOF,
            pair.span_ordinal,
            pair.old_chunk.payload_sha256,
            pair.new_chunk.payload_sha256,
        ])
    ).hexdigest()
    assert pair.pair_id == expected


def test_05_split_and_merge_are_excluded():
    split = align(["A", "OLD", "C"], ["A", "NEW1", "NEW2", "C"])
    merge = align(["A", "OLD1", "OLD2", "C"], ["A", "NEW", "C"])
    assert not split.pairs and split.exclusions[0].reason_code == REASON_SPLIT
    assert not merge.pairs and merge.exclusions[0].reason_code == REASON_MERGE


def test_all_unmatched_span_shapes_have_explicit_reason_codes():
    multi_insert = align(["A"], ["X", "Y", "A"])
    multi_delete = align(["X", "Y", "A"], ["A"])
    ambiguous = align(["A", "X", "Y", "C"], ["A", "U", "V", "C"])
    assert multi_insert.exclusions[0].reason_code == REASON_MULTI_INSERTION
    assert multi_delete.exclusions[0].reason_code == REASON_MULTI_DELETION
    assert ambiguous.exclusions[0].reason_code == REASON_AMBIGUOUS


def test_06_duplicate_equal_paragraphs_have_lexicographic_lcs():
    old = ["A", "A", "B"]
    new = ["A", "B", "A"]
    assert stable_lcs_matches(old, new) == ((0, 0), (1, 2))
    assert stable_lcs_matches(old, new) == stable_lcs_matches(old, new)


def test_07_reorder_is_excluded_not_paired():
    result = align(["A", "B", "C"], ["B", "A", "C"])
    assert not result.pairs
    assert [e.reason_code for e in result.exclusions] == [REASON_REORDER]


def test_08_heading_rename_moves_section_identity_and_is_excluded():
    old = chunk_document("doc.md", "# Old\n\ntext", "md", TOK)
    new = chunk_document("doc.md", "# New\n\ntext", "md", TOK)
    result = align_documents(
        source="kubernetes_website",
        parent_commit="1" * 40,
        child_commit="2" * 40,
        document_path="doc.md",
        old_chunks=old,
        new_chunks=new,
    )
    assert not result.pairs
    assert {e.reason_code for e in result.exclusions} == {
        REASON_SECTION_REMOVED, REASON_SECTION_ADDED
    }


def test_09_rollback_retains_three_temporal_versions():
    versions = [
        TemporalSectionVersion("1" * 40, chunks([state]))
        for state in ["A", "B", "A"]
    ]
    assert collapse_consecutive_versions(versions) == tuple(versions)
    with_duplicate = [versions[0], versions[0], versions[1], versions[2]]
    assert collapse_consecutive_versions(with_duplicate) == tuple(versions)


def test_10_fixture_and_reason_hashes_stable_across_processes():
    fixture = {
        "matches": stable_lcs_matches(["A", "A", "B"], ["A", "B", "A"]),
        "reasons": [REASON_INSERTION, REASON_DELETION, REASON_SPLIT, REASON_MERGE],
    }
    local = hashlib.sha256(canonical_json_bytes(fixture)).hexdigest()
    root = str(Path(__file__).resolve().parents[1])
    script = f"""
import hashlib, sys
sys.path.insert(0, {root!r})
from w0prep.alignment import stable_lcs_matches, REASON_INSERTION, REASON_DELETION, REASON_SPLIT, REASON_MERGE
from w0prep.chunking import canonical_json_bytes
x={{'matches': stable_lcs_matches(['A','A','B'], ['A','B','A']), 'reasons':[REASON_INSERTION,REASON_DELETION,REASON_SPLIT,REASON_MERGE]}}
print(hashlib.sha256(canonical_json_bytes(x)).hexdigest())
"""
    fresh = subprocess.check_output([sys.executable, "-c", script], text=True).strip()
    assert fresh == local


def test_chunker_exact_breadcrumb_payload_and_occurrence():
    raw = "---\ntitle: ignored\n---\n# API   Guide\n\nFirst.  \r\n\r\nSecond."
    got = chunk_document("content/en/docs/x.md", raw, "markdown", TOK)
    assert [c.payload for c in got] == [
        "[SECTION] api guide\n\nFirst.",
        "[SECTION] api guide\n\nSecond.",
    ]
    assert [c.occurrence for c in got] == [0, 1]


def test_markdown_fence_heading_is_body_and_rst_directive_is_not_heading():
    md = chunk_document("x.md", "# H\n\n```\n# not heading\n```", "md", TOK)
    assert len(md) == 1 and "# not heading" in md[0].payload
    rst = chunk_document("x.rst", "Title\n=====\n\n.. note::\n\n   -----", "rst", TOK)
    assert len(rst) == 2
    assert all(c.section_path == "title" for c in rst)


def test_root_empty_section_crlf_invalid_utf8_and_multibyte_split():
    root = chunk_document("x.md", "root\r\n\r\n# Empty\r\n", "md", TOK)
    assert len(root) == 1 and root[0].section_path == "<root>"
    with raises(ChunkingError, match="INVALID_UTF8"):
        chunk_document("x.md", b"\xff", "md", TOK)
    split = chunk_document("x.md", "# H\n\n甲乙丙丁", "md", TOK, max_payload_tokens=13)
    assert "".join(c.payload.split("\n\n", 1)[1] for c in split) == "甲乙丙丁"


def test_heading_budget_overflow_and_no_whitespace_overcap_split():
    with raises(ChunkingError, match="HEADING_OVER_CAP"):
        chunk_document("x.md", "# " + "H" * 30 + "\n\nx", "md", TOK, max_payload_tokens=10)
    got = chunk_document("x.md", "# H\n\nabcdefghij", "md", TOK, max_payload_tokens=13)
    assert len(got) > 1
    assert "".join(c.payload.split("\n\n", 1)[1] for c in got) == "abcdefghij"


def test_boundary_pair_id_and_heading_component_breadcrumb_are_exact():
    result = align(["OLD"], ["NEW"])
    pair = result.pairs[0]
    expected = hashlib.sha256(
        canonical_json_bytes([
            pair.source, pair.parent_commit, pair.child_commit,
            pair.document_path, pair.section_path,
            BOUNDARY_BOF, BOUNDARY_EOF, 0,
            pair.old_chunk.payload_sha256, pair.new_chunk.payload_sha256,
        ])
    ).hexdigest()
    assert pair.pair_id == expected

    got = chunk_document("x.md", "# API/Guide\n\ntext", "md", TOK)
    assert got[0].payload == "[SECTION] api/guide\n\ntext"
    assert canonical_chunk_id("kubernetes_website", got[0]) == hashlib.sha256(
        canonical_json_bytes([
            "kubernetes_website", "x.md", "api/guide", 0,
            got[0].payload_sha256,
        ])
    ).hexdigest()


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value, description=name))
    return suite
