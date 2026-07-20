from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from w0prep.alignment import align_documents  # noqa: E402
from w0prep.chunking import chunk_document  # noqa: E402
from w0prep.workload import (  # noqa: E402
    BlobReader,
    _closure_gate,
    _control_c,
    _history_oid_index,
    enumerate_candidates,
    pair_row,
)


class TinyTokenizer:
    def __call__(
        self, text, *, add_special_tokens=False, return_offsets_mapping=False
    ):
        offsets = [(i, i + 1) for i, char in enumerate(text) if not char.isspace()]
        result = {"input_ids": list(range(len(offsets)))}
        if return_offsets_mapping:
            result["offset_mapping"] = offsets
        return result


TOK = TinyTokenizer()
POLICY = {"git_mode": "100644", "min_bytes": 1, "max_bytes": 1024 * 1024}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def write(repo: Path, relative: str, contents: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class SyntheticRepoTest(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name)
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.email", "w0@example.invalid")
        git(repo, "config", "user.name", "W0 Test")
        return temporary, repo

    @staticmethod
    def spec(repo: Path, lo: str, hi: str) -> dict[str, str]:
        return {
            "repo": str(repo),
            "lo": lo,
            "hi": hi,
            "path_regex": r"^docs/[^/]+\.md$",
            "format": "markdown",
        }

    def test_merge_is_diffed_against_first_parent_and_unrelated_change_is_allowed(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        write(repo, "docs/a.md", "# H\n\nbase\n")
        lo = commit(repo, "base")

        git(repo, "checkout", "-b", "topic")
        write(repo, "docs/a.md", "# H\n\ntopic\n")
        commit(repo, "topic eligible change")

        git(repo, "checkout", "main")
        write(repo, "notes.txt", "main side\n")
        commit(repo, "unrelated main change")
        git(repo, "merge", "--no-ff", "topic", "-m", "merge topic")
        merge_commit = git(repo, "rev-parse", "HEAD")
        self.assertEqual(len(git(repo, "rev-list", "--parents", "-n", "1", merge_commit).split()), 3)

        # One eligible M plus an unrelated non-eligible M is still admissible.
        write(repo, "docs/a.md", "# H\n\nafter merge\n")
        write(repo, "notes.txt", "also changed\n")
        hi = commit(repo, "eligible plus unrelated")

        candidates, audit, _ = enumerate_candidates(
            "synthetic", self.spec(repo, lo, hi), POLICY
        )
        candidate_children = {candidate.child for candidate in candidates}
        self.assertIn(merge_commit, candidate_children)
        self.assertIn(hi, candidate_children)
        merge_row = next(row for row in audit if row["child"] == merge_commit)
        self.assertEqual(merge_row["decision"], "CANDIDATE")
        self.assertEqual(merge_row["parent"], git(repo, "rev-parse", f"{merge_commit}^1"))
        self.assertEqual(merge_row["eligible_record_count"], 1)

    def test_multi_eligible_commit_remains_in_control_c_history(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        write(repo, "docs/a.md", "# H\n\nleft\n\nvery-old\n\nright\n")
        write(repo, "docs/b.md", "# H\n\nb0\n")
        lo = commit(repo, "base")

        write(repo, "docs/a.md", "# H\n\nleft\n\nintermediate\n\nright\n")
        write(repo, "docs/b.md", "# H\n\nb1\n")
        multi = commit(repo, "two eligible documents")
        write(repo, "docs/a.md", "# H\n\nleft\n\nnew\n\nright\n")
        hi = commit(repo, "main pair")

        spec = self.spec(repo, lo, hi)
        candidates, audit, order = enumerate_candidates("synthetic", spec, POLICY)
        self.assertEqual([candidate.child for candidate in candidates], [hi])
        multi_row = next(row for row in audit if row["child"] == multi)
        self.assertEqual(multi_row["decision"], "EXCLUDE_NOT_EXACTLY_ONE_ELIGIBLE_PATH")

        history_index = _history_oid_index(spec, POLICY, audit)
        oid_history = history_index.versions
        self.assertEqual(set(oid_history["docs/a.md"]), {lo, multi, hi})

        reader = BlobReader(repo, POLICY)
        chunk_history = {
            "docs/a.md": {
                revision: chunk_document(
                    "docs/a.md", reader.read(version.oid), "markdown", TOK
                )
                for revision, version in oid_history["docs/a.md"].items()
            }
        }
        segments = {
            "docs/a.md": {
                revision: version.segment
                for revision, version in oid_history["docs/a.md"].items()
            }
        }
        candidate = candidates[0]
        aligned = align_documents(
            source="synthetic",
            parent_commit=candidate.parent,
            child_commit=candidate.child,
            document_path=candidate.path,
            old_chunks=chunk_history["docs/a.md"][multi],
            new_chunks=chunk_history["docs/a.md"][hi],
        )
        self.assertEqual(len(aligned.pairs), 1)
        real = aligned.pairs[0]
        selected = [pair_row(real, commit_order=candidate.order, tokenizer=TOK)]
        controls, missing = _control_c(
            selected,
            {real.pair_id: real},
            chunk_history,
            order,
            segments,
        )
        self.assertFalse(missing)
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["control_commit"], lo)
        self.assertEqual(controls[0]["anchor_payload"].splitlines()[-1], "very-old")

    def test_delete_and_readd_starts_new_control_c_lineage_segment(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        write(repo, "docs/a.md", "# H\n\nleft\n\nold-before-delete\n\nright\n")
        lo = commit(repo, "old lifetime")
        (repo / "docs/a.md").unlink()
        deleted = commit(repo, "delete path")
        write(repo, "docs/a.md", "# H\n\nleft\n\nnew lifetime\n\nright\n")
        readded = commit(repo, "re-add same path")
        write(repo, "docs/a.md", "# H\n\nleft\n\ntarget\n\nright\n")
        hi = commit(repo, "modify new lifetime")

        spec = self.spec(repo, lo, hi)
        candidates, audit, order = enumerate_candidates("synthetic", spec, POLICY)
        self.assertEqual([candidate.child for candidate in candidates], [hi])
        history_index = _history_oid_index(spec, POLICY, audit)
        versions = history_index.versions["docs/a.md"]
        self.assertEqual(versions[lo].segment, 0)
        self.assertEqual(versions[readded].segment, 1)
        self.assertEqual(versions[hi].segment, 1)
        events = {
            (row["commit"], row["event"]) for row in history_index.segment_audit
        }
        self.assertIn((deleted, "TOMBSTONE_DELETE"), events)
        self.assertIn((readded, "SEGMENT_START_ADD"), events)

        reader = BlobReader(repo, POLICY)
        chunk_history = {
            "docs/a.md": {
                revision: chunk_document(
                    "docs/a.md", reader.read(version.oid), "markdown", TOK
                )
                for revision, version in versions.items()
            }
        }
        segments = {
            "docs/a.md": {
                revision: version.segment for revision, version in versions.items()
            }
        }
        candidate = candidates[0]
        aligned = align_documents(
            source="synthetic",
            parent_commit=candidate.parent,
            child_commit=candidate.child,
            document_path=candidate.path,
            old_chunks=chunk_history["docs/a.md"][readded],
            new_chunks=chunk_history["docs/a.md"][hi],
        )
        self.assertEqual(len(aligned.pairs), 1)
        real = aligned.pairs[0]
        selected = [pair_row(real, commit_order=candidate.order, tokenizer=TOK)]
        controls, missing = _control_c(
            selected,
            {real.pair_id: real},
            chunk_history,
            order,
            segments,
        )
        self.assertFalse(controls)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["reason"], "MISSING_NO_NONADJACENT_VERSION")
        self.assertNotIn("old-before-delete", str(controls))

    def test_short_reference_and_control_minima_are_hard_closure_failures(self):
        config = {
            "fixed_reference": {"universe_size": 8448},
            "sampling": {
                "min_documents_per_control_per_source": 64,
                "min_pairs_per_control_per_source": 128,
            },
        }
        failed = _closure_gate(
            config,
            fixed_reference_count=8447,
            control_a_counts={"documents": 64, "pairs": 128},
            control_c_counts={"documents": 63, "pairs": 127},
        )
        self.assertEqual(failed["status"], "FAIL-W0-WORKLOAD-CLOSURE")
        self.assertFalse(failed["checks"]["fixed_reference_exact_universe"])
        self.assertFalse(failed["checks"]["control_c_min_documents"])
        self.assertFalse(failed["checks"]["control_c_min_pairs"])

        passed = _closure_gate(
            config,
            fixed_reference_count=8448,
            control_a_counts={"documents": 64, "pairs": 128},
            control_c_counts={"documents": 64, "pairs": 128},
        )
        self.assertEqual(passed["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
