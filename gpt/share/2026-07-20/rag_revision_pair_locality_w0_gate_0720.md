# RAG Document Revision：Paired-Replacement Locality W0 Gate

**Date:** 2026-07-20  
**Repository:** `Metafora072/VectorDBChat`  
**Decision:** Reject the broad document-group A0; authorize only a workload-level paired-replacement locality gate.

## 1. Decision on the current prelaunch

```text
Broad Document-Group Update A0 = STOP-BROAD-GROUP-A0
Route A: instrumentation + Greator/Slipstream implementation = REJECT
Route B: negative-only full graph trace = REJECT
Salvage W0: old-chunk → new-chunk locality = APPROVE-W0-PAIR-LOCALITY
```

Reasons:

1. Greator already performs small-batch affected-vertex deduplication, page-aware I/O deduplication, and localized repair.
2. FreshDiskANN consolidation already merges repair candidates across the deletion batch and prunes each affected vertex once.
3. Slipstream already exploits insertion-stream locality through warm starts.
4. Existing HNSW implementations and MN-RU already cover true vector updates / replacement-style graph maintenance.
5. The current Atlas binaries expose `0/7` required per-update traces.
6. A valid strong-baseline A0 would require implementing both instrumentation and prior-work mechanisms before the workload premise is established.
7. The corrected full design contains 76,800 executions plus derived oracle records and violates the registered eight-hour bound.

The broad experiment has an unfavorable cost-to-information ratio. A positive result without strong baselines is not actionable; adding the baselines first is premature system implementation.

## 2. Narrow surviving question

The only potentially ANN-specific signal is the explicit old→new mapping of a modified chunk.

For one modified chunk:

```text
old vector x_old
→ source revision
→ new vector x_new
```

Ask:

> Is `x_old` a substantially better structural starting point for `x_new` than matched controls, such that the old node's local neighborhood contains a large portion of the new vector's target neighborhood?

This is a necessary condition for any future replacement-aware disk-graph mechanism.

It does not assume that document identity itself matters. The index-visible signal may be only geometric proximity.

## 3. Why this W0 comes before graph instrumentation

The proposed broad group mechanisms decompose into already occupied components:

```text
deletion batch deduplication → FreshDiskANN / Greator
page-level repair deduplication → Greator
sequential insertion warm-start → Slipstream
generic page reuse → cache
vector replacement/update → HNSW update / MN-RU
```

A remaining mechanism would need to exploit the actual old→new revision pair.

If old and new vectors do not inherit local neighborhoods, there is no reason to preserve the old node as an anchor, reuse its neighbors, update in place, seed graph search from it, or jointly schedule delete-old and insert-new.

Therefore W0 tests this necessary condition without touching the disk-index implementation.

## 4. Frozen workload

### 4.1 Sources

Use exactly two immutable Git repositories:

```text
kubernetes/website
python/cpython (Doc/ only)
```

Do not use Wikipedia in W0. API recovery and wikitext processing add no value to the necessary-condition test.

Freeze repository URL, commit SHA range, first-parent policy, file extensions and directory filters, rename/add/delete treatment, and inclusion/exclusion manifest.

### 4.2 Revision selection

Select commits that modify one eligible documentation file. Recover parent and child contents using the frozen first-parent rule. Only retain revisions with at least one deterministically paired modified chunk.

### 4.3 Chunk pairing

Use one structure-aware chunker in W0.

A chunk identity is:

```text
(document path, normalized section path, occurrence index)
```

For a chunk identity present in both parent and child:

- identical content hash → unchanged; exclude;
- different content hash → one old→new modified pair.

Chunks existing on only one side are additions/deletions and are excluded from W0.

Do not pair chunks using embedding similarity or a learned threshold.

### 4.4 Embeddings

Use exactly two frozen CPU-compatible models:

```text
sentence-transformers/all-MiniLM-L6-v2
nomic-ai/nomic-embed-text-v1.5
```

Freeze model revision, tokenizer revision, weight hashes, normalization, and metric. No GPU, LLM, or API.

## 5. Background corpus and exact neighborhood oracle

For each source and frozen checkpoint, construct a background corpus of eligible chunks.

For each old→new pair:

- exclude both pair members from the background;
- compute exact distances from `x_old` and `x_new`;
- compute exact top-R neighborhoods for `R = 16, 32, 64`.

These R values are analysis scales, not tuned system parameters.

Construct an exact kNN graph over the frozen background only for offline neighborhood analysis. This is not an ANN performance experiment.

## 6. Metrics

For each pair, compute:

### 6.1 Revision displacement

```text
distance(x_old, x_new)
```

### 6.2 Old-node rank

Rank of `x_old` when searching for `x_new` in the active corpus where `x_old` is present.

### 6.3 Exact neighborhood overlap

For each R:

```text
J_R = |NN_R(x_old) ∩ NN_R(x_new)| / |NN_R(x_old) ∪ NN_R(x_new)|
```

### 6.4 One-hop coverage

```text
Coverage1_R = |NN_R(x_new) ∩ ({x_old} ∪ NN_R(x_old))| / R
```

### 6.5 Two-hop coverage

```text
H2_R(x_old) = {x_old} ∪ NN_R(x_old) ∪ ⋃_{v ∈ NN_R(x_old)} NN_R(v)
Coverage2_R = |NN_R(x_new) ∩ H2_R(x_old)| / R
```

Report the size of `H2_R`; high coverage obtained only by an enormous candidate set is not useful.

### 6.6 Candidate efficiency curve

Order candidates by old node, old node's exact neighbors, then neighbors-of-neighbors. Report new-neighborhood recall as a function of candidate count. Do not select a post-hoc cutoff.

## 7. Paired controls

### Control A: random cross-document pair

For every real pair, select an old control vector from a different document, matched on source, embedding model, chunk token-length stratum, and active checkpoint. The target remains `x_new`.

### Control B: distance-matched cross-document pair

Select a vector `z` from a different document whose distance to `x_new` is closest to `distance(x_old, x_new)`. Use deterministic tie-breaking.

This tests whether revision lineage gives any structure beyond pure geometric proximity.

### Control C: non-adjacent same-section revision

Where available, pair the same section's child vector with a non-adjacent historical version under the frozen first-parent history. This tests whether temporal adjacency matters.

Only complete paired sets enter each corresponding comparison. Missing-control rules are frozen before metrics are inspected.

## 8. Statistical protocol

The inference unit is a source-document cluster, not an individual chunk pair.

Use document-clustered paired bootstrap confidence intervals.

Primary comparisons:

```text
real vs random
real vs distance-matched cross-document
adjacent revision vs non-adjacent same-section
```

For each R, compare old-node rank, neighborhood Jaccard, one-hop coverage, and two-hop coverage at matched candidate count.

Do not use an arbitrary percentage threshold.

A positive signal requires the lower confidence bound of real-pair advantage over the relevant control to be greater than zero, consistently across both sources, both embedding models, and at least two of the three R values. Correct for the frozen family of primary comparisons.

## 9. Required outputs

Codex produces:

```text
codex/share/2026-07-20/rag_revision_pair_locality_w0_prelaunch_0720.md
codex/share/2026-07-20/rag_revision_pair_locality_w0_result_0720.md
```

Prelaunch must bind source snapshots, first-parent and rename policy, section identity rules, multiset occurrence handling, model/tokenizer/weight hashes, background checkpoint, exact-neighbor implementation, control generator, document-clustered statistics, resource guards, and source/config/result hashes.

No measurement runs before exact:

```text
PASS-W0-PRELAUNCH
```

## 10. Resource bounds

```text
GPU = 0
LLM/API = 0
NVMe allocation <= 10 GiB
peak RSS <= 24 GiB
wall clock <= 4 hours
sources = 2
embedding models = 2
no DGAI/OdinANN modification
no physical NVMe profiling
```

If exact all-pairs computation exceeds the resource limit, use a frozen exact blockwise implementation on a preregistered corpus sample. Do not silently substitute approximate neighbors.

## 11. Final labels

### `HOLD-PAIR-LOCALITY-NOVELTY-REVIEW`

Use only when real adjacent old→new pairs dominate random controls, also dominate distance-matched cross-document controls on neighborhood inheritance, temporal adjacency improves over non-adjacent same-section versions, results reproduce across both sources and both models, and candidate-efficiency curves improve at matched candidate counts.

This label authorizes only a paper/code novelty review against hnswlib true updates, MN-RU, Greator, IP-DiskANN, Slipstream, and in-place vector replacement/update systems. It does not authorize disk-index implementation.

### `HOLD-GEOMETRIC-REPLACEMENT-ONLY`

Use when real pairs beat random controls but do not beat distance-matched cross-document controls. Document revision identity is then not a distinct index signal.

### `KILL-NO-PAIR-LOCALITY`

Use when real pairs do not consistently beat random controls or old-node local neighborhoods do not cover the new vector's neighborhood efficiently. This closes both paired-replacement and the broader document-group direction.

### `KILL-NO-TEMPORAL-LINEAGE-SIGNAL`

Use when same-section non-adjacent versions perform as well as adjacent revisions and the remaining effect is fully explained by static semantic similarity.

### `FAIL-W0-WORKLOAD-CLOSURE`

Use for source, pairing, exact-neighbor, control, provenance, or statistical closure failures.

## 12. Stop line

After W0, stop.

Do not add graph trace hooks, implement Greator or Slipstream, modify DGAI/OdinANN, implement update-in-place, reuse old adjacency, run NVMe experiments, or revive broad document-group batching.

Any positive W0 first receives a separate novelty gate.
