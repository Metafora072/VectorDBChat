# Paired-Replacement Locality W0：Prelaunch Amendment and Artifact-Preparation Authorization

**Date:** 2026-07-20  
**Repository:** `Metafora072/VectorDBChat`  
**Reviewed prelaunch:** `codex/share/2026-07-20/rag_revision_pair_locality_w0_prelaunch_0720.md`  
**Decision:** Conditional authorization for artifact/runner preparation only. Measurement remains unauthorized.

## 1. Current ruling

```text
W0 design direction = RETAIN
artifact/runner preparation = CONDITIONALLY AUTHORIZED
measurement = NOT AUTHORIZED
PASS-W0-PRELAUNCH = NOT YET ISSUED
```

The frozen sources, model artifacts, exact-neighborhood oracle, paired controls, clustered inference, resource guards, and provenance plan are sufficiently developed for a preparation stage.

However, the current old→new pairing rule has one decisive validity flaw that must be corrected before any workload is materialized.

## 2. Decisive pairing flaw

The current identity:

```text
(document_path, normalized_section_path, occurrence)
```

pairs the old and new paragraph at the same ordinal position.

This is not stable under an insertion or deletion before that paragraph.

Example:

```text
old: [A, B, C]
new: [X, A, B, C]
```

Ordinal pairing would incorrectly create:

```text
A→X
B→A
C→B
```

and treat `C` as deleted.

These are not source revisions of the same chunk. They are alignment artifacts. They can either destroy a true locality signal or manufacture a misleading one.

A fixture that merely records this behavior is insufficient; the generator must prevent it.

## 3. Required conservative pairing rule

Within each unchanged `(document_path, normalized_section_path)`, construct ordered old/new chunk sequences.

### 3.1 Exact anchors

Use deterministic occurrence-aware sequence alignment on exact `payload_sha256` values:

1. Compute a stable longest common subsequence of exact payload hashes.
2. Duplicate equal hashes are occurrence-aware and resolved with a frozen lexicographic dynamic-programming tie-break.
3. Exact aligned hashes are unchanged anchors and are excluded from the pair set.
4. No embedding distance, fuzzy text threshold, or manual alignment is allowed.

### 3.2 Modified-pair admission

For every unmatched span between consecutive exact anchors:

```text
old unmatched span length = a
new unmatched span length = b
```

Admit one old→new modified pair only when:

```text
a = 1 and b = 1
```

Exclude with explicit reason codes:

```text
1→0 deletion
0→1 insertion
1→many split
many→1 merge
many→many ambiguous rewrite/reorder
```

Leading and trailing unmatched spans follow the same rule.

This deliberately sacrifices recall of modified chunks in exchange for high-precision replacement identity.

### 3.3 Pair identity

The pair ID must bind:

- source;
- parent and child commit;
- document path;
- normalized section path;
- left and right exact-anchor identities, or boundary sentinels;
- unmatched-span ordinal;
- old/new payload hashes.

The old/new paragraph ordinal may be recorded, but it must not define identity across revisions.

### 3.4 Control C

Non-adjacent same-section histories must be constructed with the same conservative exact-anchor/span rule. Do not compare versions by raw ordinal occurrence.

## 4. Mandatory fixtures

The runner must prove:

1. Prefix insertion does not create cascading replacements.
2. Middle insertion preserves A/A, B/B, C/C exact anchors.
3. Deletion does not shift all later pairs.
4. One old paragraph replaced by one new paragraph yields exactly one pair.
5. Split and merge are excluded.
6. Duplicate equal paragraphs receive deterministic occurrence-aware alignment.
7. Reordering is excluded rather than arbitrarily paired.
8. Heading rename moves the section identity and is excluded.
9. Rollback `A→B→A` remains three temporal versions for Control C.
10. Fixture output and reason-code hashes are stable across fresh processes.

## 5. Fixed-reference-corpus claim boundary

The prelaunch uses a common `hi` reference corpus, not the exact active corpus at each historical revision.

Therefore rename:

```text
active corpus
```

to:

```text
fixed reference corpus
```

throughout the runner and report.

W0 may conclude only:

> Under a frozen reference vector population, adjacent old revisions inherit more exact local-neighborhood structure than matched controls.

It may not claim:

- actual Vamana/HNSW search acceleration;
- actual update-time active-graph locality;
- SSD page reuse;
- reduced insertion hops;
- safe adjacency reuse.

Any positive W0 still requires a separate novelty review and later active-snapshot/index gate.

## 6. Authorized preparation work

Codex may now perform only:

1. selectively materialize the frozen source blobs;
2. implement the corrected chunker/alignment/pair/control generators;
3. generate decoded inclusion/exclusion, pair, background, reserve, and control manifests;
4. download and hash only the pinned required Nomic artifacts;
5. run MiniLM and Nomic deterministic CPU canaries;
6. implement and unit-test the exact top-321 oracle;
7. implement clustered statistics and final-label classifier;
8. run the projection canary;
9. hash runner, tests, config, manifests, environment, and projected resource records;
10. update the prelaunch report.

No outcome metrics over the complete selected workload may be computed.

## 7. Final run-gate requirements

Return with exact:

```text
PASS-W0-PRELAUNCH
```

only if all are closed:

- conservative alignment fixtures;
- minimum 64 documents and 128 complete pairs per source for each required comparison after the stricter pairing;
- final core/reserve/control manifests;
- both model canaries;
- exact-oracle full-sort equivalence tests;
- runner/config/test hashes;
- measured wall/RSS/storage projection within guards;
- fixed-reference wording;
- no unregistered fallback.

Otherwise return:

```text
FAIL-W0-WORKLOAD-CLOSURE
```

or a precise `RETURN-FOR-REVISION`, without measurement.

## 8. Stop line

This authorization does not permit:

- full W0 measurement;
- DGAI/OdinANN changes;
- ANN graph construction or search profiling;
- NVMe profiling;
- update-in-place;
- old-adjacency reuse;
- Greator/Slipstream implementation;
- broad document-group revival.
