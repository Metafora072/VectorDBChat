# Correlated Document-Group Updates in Disk-Resident Graph ANN: A0 Prelaunch

**Date:** 2026-07-20
**Author:** Codex (executor/reviewer), synthesized from two Codex analysis sessions
**Gate:** `rag_document_group_update_a0_gate_0720.md`
**Input:** Claude's `rag_document_group_update_landscape_and_trace_design_0720.md`
**Status:** Independent prelaunch review

---

## 1. Primary-Source Novelty Audit

### 1.1 Corrections to Claude's prior-work descriptions

#### Greator (Claude listed as "Topology-aware localized update")

**Claude's description:** "Page-level localized repair: identifies affected nodes within a bounded neighborhood and repairs only those, avoiding full-index scan. [...] Locality-aware but not group-aware. Repairs one deletion at a time using local topology."

**Actual mechanism (verified from VLDB 2025 paper, arXiv:2503.00402):**
- Greator processes **small batches** (0.1–8% of dataset), not single deletions.
- It scans a lightweight topology index to locate incoming neighbors affected by **all deleted vertices in the batch**, implicitly deduplicating affected vertices.
- Uses a **page-aware cache structure ΔG** that organizes reverse edges by page, minimizing redundant reads/writes of the same page.
- Uses Adaptive Similar Neighbor Replacement (ASNR) instead of RobustPrune for small deletions — avoids expensive prune entirely when deletion count is small.
- Each affected vertex is still repaired independently (no combined prune across vertices).

**Impact on novelty:** Greator already has (a) batch-level repair-target dedup, (b) page-level I/O dedup via ΔG, (c) avoidance of full-index scan. This means "repair-target deduplication + page merge" is NOT a blank space. Claude's description of "repairs one deletion at a time" is incorrect.

#### FreshDiskANN batch consolidation

**Claude's description:** "Batch deletion is global, not group-local. Does co-locate affected vertices only because it scans everything."

**Actual mechanism (verified from arXiv:2105.09613):**
- FreshDiskANN's consolidation algorithm first computes the full set of affected vertices for the **entire batch** of deletions.
- For each affected vertex, it collects candidate neighbors from all remaining (non-deleted) neighbors of deleted nodes.
- Each affected vertex undergoes RobustPrune **once** with the merged candidate set.
- The "global scan" is for identifying affected vertices (who has edges pointing to deleted nodes), but the actual repair per vertex already merges information from multiple deletions.

**Impact on novelty:** FreshDiskANN batch consolidation already deduplicates: each affected vertex is pruned once regardless of how many of its deleted neighbors are in the batch. The scan is global, but the per-vertex work is already deduplicated.

#### Slipstream

**Claude's description is mostly accurate.** Slipstream exploits stream locality for warm-starting insertion search. Key limitation correctly identified: insertion-only, no deletion/repair, no explicit group concept.

**Additional note:** Slipstream's warm-start would naturally apply to document-group insertions if chunks are processed sequentially. This is a baseline that must be tested — if the group simply processes insertions in sequence, Slipstream's warm-start already captures search-path overlap for free.

#### IP-DiskANN

**Claude's description is accurate.** Per-point in-place updates, no batch concept.

#### DGAI and OdinANN

**Cannot fully verify from public sources.** These are PZ's own implementations. Instrumentation capabilities must be checked against actual code.

### 1.2 Missing prior work

| System | Year | Relevance |
|--------|------|-----------|
| **CANDOR-Bench** | 2026 | Benchmarks continuous ANN under dynamic open-world streams. May define workload patterns relevant to document revision churn. |
| **Leveraging I/O Stalls for Efficient Scheduling in ANNS** (arXiv:2605.19335) | 2026 | Uses I/O stall time for useful computation during ANN updates. Could affect timing measurements. |

### 1.3 Novelty boundary assessment

After correcting Claude's prior-work descriptions, the novelty boundary is tighter:

**Already exists in some form:**
- Repair-target dedup across a batch (Greator, FreshDiskANN consolidation)
- Page-level I/O dedup within a batch (Greator's ΔG)
- Warm-start search for sequential nearby insertions (Slipstream)
- Localized repair without full-index scan (Greator)
- Avoidance of RobustPrune for small update batches (Greator's ASNR)

**Potentially novel (unverified):**
- Exploiting a-priori-known group boundary to pre-compute shared search state (no prior work does this)
- Document identity as a signal beyond geometric proximity (untested empirically)
- Joint optimization of delete-old + insert-new within a revision group (no prior work treats old↔new chunk pairs as a unit)

**The critical question is whether the "potentially novel" items provide measurable benefit BEYOND what Greator + Slipstream + page cache already capture.**

---

## 2. Data Source Reproducibility Check

### 2.1 kubernetes/website

- **Commits:** >15,000 commits (verified via GitHub API)
- **Structure:** Markdown files under `content/en/docs/`
- **License:** CC-BY-4.0 (research use allowed)
- **Recovery:** `git show <commit>:<path>` recovers old/new content
- **Verdict:** ✅ SUITABLE

### 2.2 rust-lang/book

- **Commits:** ~3,000 commits
- **Structure:** Markdown files under `src/`
- **License:** MIT + Apache-2.0
- **Recovery:** Same git mechanism
- **Concern:** Smaller commit count; may need to supplement with python/cpython Docs (reStructuredText under `Doc/`, PSF license, >5,000 doc-touching commits)
- **Verdict:** ✅ SUITABLE (with python/cpython as fallback)

### 2.3 Wikipedia revision subset

- **Recovery:** MediaWiki API `action=query&prop=revisions&rvprop=content`
- **Concerns:**
  1. **API rate limits:** 200 requests/minute for anonymous, 500 for logged-in users. Recovering 200 revision groups × 2 versions each = 400 API calls minimum — feasible but slow.
  2. **Hidden/deleted revisions:** Some revisions may be suppressed (copyright, BLP policy). The experiment must handle missing revisions gracefully.
  3. **License:** CC-BY-SA 3.0. Research use is fine, but derived datasets must carry attribution.
  4. **Non-deterministic content:** Templates, transclusions, and parser functions may resolve differently at different times. Must fetch and freeze wikitext source, not rendered HTML.
  5. **Document structure:** Wikitext markup differs fundamentally from Markdown. Chunking policy must handle both.
- **Verdict:** ⚠️ SUITABLE WITH CAVEATS — must pre-fetch and freeze all revision content before experiment; must handle missing revisions; must use wikitext, not rendered HTML.

---

## 3. Frozen Group/Control Generator

### 3.1 Revision group sampling algorithm

```
Input: git repository, max_groups_per_source, group_size_strata
Output: frozen list of revision groups

1. git log --diff-filter=M --name-only  →  list of (commit, modified_files)
2. Filter: keep commits that modify exactly ONE file matching *.md or *.rst
3. For each (commit, file):
   a. old_content = git show commit~1:file
   b. new_content = git show commit:file
   c. old_chunks = chunk(old_content, policy)
   d. new_chunks = chunk(new_content, policy)
   e. For each chunk: content_hash = SHA-256(normalize(chunk_text))
   f. unchanged = {c : content_hash(c) in old_hashes AND content_hash(c) in new_hashes}
   g. deleted = old_chunks - unchanged
   h. inserted = new_chunks - unchanged
   i. group = deleted ∪ inserted
   j. If |group| < 2: skip (trivial revision)
   k. Record: (commit, file, group, old_chunks, new_chunks, unchanged)
4. Stratify by group size: [2-5], [6-15], [16+]
5. Within each stratum, sample uniformly up to max_groups_per_source / 3
6. Freeze with deterministic seed (record seed value)
```

### 3.2 Control generation

**Control A (Random batch):**
```
For each real group G of size g:
  1. Sample g vectors uniformly from active corpus (excluding G's vectors)
  2. Match insert/delete ratio: if G has d deletes and i inserts,
     sample d existing vectors to "delete" and i random positions to "insert"
  3. Match chunk-length distribution: sort G's chunks by length,
     sample control chunks with closest length match
  4. Seed: hash(group_id, "control_a", master_seed)
```

**Control B (Geometric cluster, cross-document):**
```
For each real group G:
  1. Compute centroid of G's embeddings
  2. Find g nearest vectors from different documents
  3. Verify: no two vectors share the same document_id
  4. Verify: pairwise distance distribution within 20% of G's
     (if not, widen search radius and retry, max 3 retries)
  5. Match insert/delete ratio
  6. Seed: hash(group_id, "control_b", master_seed)
```

**Control C (Same-document, broken lineage):**

⚠️ **DESIGN CONCERN (from Codex analysis):** Claude's proposed Control C — "shuffle the old↔new chunk pairing within G" — is problematic. If we only shuffle which old chunk is "paired" with which new chunk, the actual set of chunks being deleted and inserted does NOT change. The graph operations are determined by which vectors are deleted and which are inserted, not by their pairing. Therefore shuffling pairing is an **ineffective control** — it produces identical graph operations.

**Revised Control C:**
```
For each real group G from document D at commit C:
  1. Find a non-adjacent revision of D (commit C' where |C' - C| >= 5 commits)
  2. Apply same chunking to D at C'~1 and C'
  3. Extract the revision group from this different revision
  4. If group sizes differ significantly (>2× ratio), skip this control pair
  5. This tests whether revision lineage matters, not just document identity
```

If no suitable non-adjacent revision exists for a document, mark this control as MISSING and exclude the pair from the Control C analysis.

---

## 4. Exact Unchanged-Chunk Matching

### 4.1 Normalization

```
normalize(text):
  1. Decode to UTF-8 (reject non-UTF-8 files)
  2. Strip trailing whitespace per line
  3. Normalize line endings to \n
  4. Strip leading/trailing blank lines
  5. Collapse runs of >2 blank lines to 2
  6. Do NOT normalize Unicode (NFC/NFD) — preserve exact source encoding
```

### 4.2 Hash computation

```
content_hash(chunk) = SHA-256(normalize(chunk.text).encode('utf-8'))
```

### 4.3 Edge cases

- **Empty chunks** (after normalization): Exclude from group. Log count.
- **Chunks below minimum size** (< 20 characters after normalization): Exclude. Log count.
- **Chunks exceeding maximum size** (> 2048 tokens): Re-split at paragraph boundary. Log.
- **Binary/non-text content**: Skip entire document. Log.

### 4.4 Verification

For each revision group, verify:
```
|deleted| + |inserted| + |unchanged| = |old_chunks| + |new_chunks| - |unchanged|
```

And: no chunk appears in both deleted and inserted sets (a chunk cannot be both removed and added — that would mean it's unchanged).

---

## 5. Embedding/Config Hashes

Before any measurement, hash and freeze:

```
FROZEN_MANIFEST:
  embedding_model_1:
    name: "sentence-transformers/all-MiniLM-L6-v2"
    revision: <exact git commit or model hub revision>
    sha256_weights: <hash of model weights file>
  embedding_model_2:
    name: "nomic-ai/nomic-embed-text-v1.5"
    revision: <exact revision>
    sha256_weights: <hash>
  chunking_policy_1:
    type: "structure-aware"
    header_levels: [2, 3]
    max_tokens: 512
    paragraph_split: true
  chunking_policy_2:
    type: "fixed-token-window"
    window_size: 256
    overlap: 0
  distance_metric: "L2"
  normalization: "unit-length"
  master_seed: <64-bit integer>
  index_system_1:
    name: "DGAI"
    binary_hash: <SHA-256 of compiled binary>
    config_hash: <SHA-256 of config file>
  index_system_2:
    name: "OdinANN"
    binary_hash: <SHA-256>
    config_hash: <SHA-256>
  source_code_hash: <SHA-256 of experiment source tree>
```

---

## 6. Index Fork Closure

### 6.1 Frozen index construction

For each (embedding model, chunking policy) combination:
1. Build a base corpus from the first N documents (before any revision is applied).
2. Construct index using standard build procedure.
3. Compute `index_fork_hash = SHA-256(concatenate(all_index_files))`.
4. Verify: `hash(DGAI_index) == hash(OdinANN_index)` is NOT required (different systems have different formats). Instead: verify that the **corpus content** is identical by hashing the vector data file.

### 6.2 Per-group fork

For each revision group and its controls:
```
1. Copy index files to 4 separate directories (serial-cold, serial-group-cache, existing-batch, union-oracle)
2. Verify: SHA-256 of each copy matches the source
3. Apply the update group/control to each copy under its respective baseline condition
4. Record pre-update and post-update index hashes
```

### 6.3 Cross-condition verification

After all updates:
- `serial-cold` and `serial-group-cache` must produce **identical** final index states (same algorithm, only caching differs).
- `existing-batch` may produce a different final state (different algorithm). Record differences.
- `union-oracle` does NOT produce a final state (it's a cost estimate only).

---

## 7. Trace Schema Review

### 7.1 Claude's schema: assessment

Claude's schema (Appendix A) is comprehensive. Missing fields:

```
# Missing from Claude's schema — must add:
group_type                    # REVISION / CONTROL_A / CONTROL_B / CONTROL_C  (Claude has control_type, OK)
wall_clock_start_ns           # per-update wall clock (nanosecond precision)
wall_clock_end_ns             # per-update wall clock end
cache_hit_page_ids            # pages served from group-local cache (for serial-group-cache condition)
cache_miss_page_ids           # pages that required SSD read
greedy_search_hops            # number of hops in greedy search (distinct from visited count)
entry_point_node_id           # which node was the search entry point
prune_invocation_count        # how many times RobustPrune was called (may differ from prune_output count)
asnr_invocation_count         # if using Greator-style ASNR, count separately
bytes_in_flight               # for I/O engine: outstanding bytes at time of each I/O
io_queue_depth_at_issue       # NVMe queue depth when I/O was submitted
```

### 7.2 I/O closure requirement

Three-layer accounting:

```
Layer 1 (Application):
  Σ page_reads_submitted × page_size = logical_bytes_read
  Σ page_writes_submitted × page_size = logical_bytes_written

Layer 2 (I/O Engine):
  Σ io_engine_read_completions × transfer_size = engine_bytes_read
  Σ io_engine_write_completions × transfer_size = engine_bytes_written

Layer 3 (Device/cgroup):
  /sys/block/<dev>/stat or cgroup io.stat: sectors_read × 512 = device_bytes_read
  /sys/block/<dev>/stat or cgroup io.stat: sectors_written × 512 = device_bytes_written

Closure:
  logical_bytes_read ≤ engine_bytes_read ≤ device_bytes_read
  (inequality due to readahead, alignment, filesystem metadata)

  Any gap must have explicit explanation:
    - OS readahead: record readahead setting, compute expected amplification
    - Filesystem metadata: estimate journal/inode bytes
    - Alignment padding: record actual vs requested sizes
    - Residual after explanation ≤ 5% of total
```

---

## 8. I/O Accounting Plan

### 8.1 Instrumentation points needed in DGAI/OdinANN

**Must verify existence in actual code (OPEN QUESTION — cannot verify from this session):**

| Instrumentation point | Purpose | Likely exists? |
|----------------------|---------|----------------|
| Graph search visited-node callback | Record V_i per update | Probably yes (needed for search) |
| Candidate set after search | Record C_i | Probably yes |
| Page read hook (before pread/io_uring submit) | Record P_i with timestamps | May need to add |
| RobustPrune input/output | Record R_i | Probably yes |
| Reverse-edge / affected-node enumeration | Record A_i | May need to add |
| Modified page tracking | Record M_i | May need to add |
| Write submission hook | Record W_i | May need to add |

**Estimated instrumentation effort:** 2–4 hooks need to be added per system. Non-trivial but feasible.

### 8.2 Group-local cache implementation

For the `serial-group-cache` baseline:
- Simple LRU or direct-mapped cache, sized to hold all pages that could be touched by a group.
- Cache scope: created at group start, destroyed at group end.
- Cache is transparent to the update algorithm — no changes to search or prune logic.
- Record cache hit/miss counts and page IDs.

### 8.3 Device-level accounting

```bash
# Before group update:
cat /sys/block/nvme0n1/stat > /tmp/io_before

# After group update:
cat /sys/block/nvme0n1/stat > /tmp/io_after

# Parse: field 3 = sectors read, field 7 = sectors written
# Alternatively: use cgroup v2 io.stat for process-level isolation
```

**Recommendation:** Use `io_uring` with submission/completion timestamps for Layer 2. Use cgroup v2 io.stat for Layer 3 (requires running experiment in a dedicated cgroup).

---

## 9. Resource Budget Confirmation

| Resource | Gate limit | Feasibility |
|----------|-----------|-------------|
| GPU | 0 | ✅ No GPU needed. Both embedding models are CPU-compatible. |
| LLM/API | 0 | ✅ No LLM/API used. |
| Distributed cluster | 0 | ✅ Single machine. |
| NVMe allocation | ≤ 80 GiB | ⚠️ Need to estimate. Base index for ~100K vectors × 768-dim × 4 bytes = ~300 MB per index. With 4 conditions × 2 systems × 2 embeddings × 2 chunking = 32 index copies ≈ 10 GiB. Plus source repos and embeddings ≈ 5 GiB. Total ≈ 15 GiB. Well within limit. |
| Peak RSS | ≤ 32 GiB | ✅ Graph indices for 100K vectors fit easily. |
| Wall clock per attempt | ≤ 8 hours | ⚠️ Depends on group count and index size. 200 groups × 4 controls × 4 conditions × 2 systems = 6,400 update runs. At ~1 second per run, ≈ 2 hours. Feasible. |
| Source repositories | ≤ 3 | ✅ kubernetes/website, rust-lang/book (or python/cpython), Wikipedia subset. |
| Revision groups | Preregistered fixed count | Use 200 per source, 600 total. Fixed before any measurement. |

---

## 10. Fail-Stop Conditions

### 10.1 KILL-CACHE-OR-BATCH-ABSORBS-GAIN

```
IF for ≥ 80% of real revision groups across all sources:
  (Serial-cold cost - Serial-group-cache cost) / (Serial-cold cost - Union-oracle cost) ≥ 0.85
THEN: KILL
REASON: Ordinary page cache captures ≥85% of the theoretical maximum benefit.
        No room for novel mechanism.
```

### 10.2 HOLD-GEOMETRIC-CORRELATION-ONLY

```
IF paired bootstrap 95% CI of:
  ReadReusePotential(real group) - ReadReusePotential(geometric control)
  AND
  RepairTargetReuse(real group) - RepairTargetReuse(geometric control)
  both contain 0
THEN: HOLD
REASON: Document identity provides no additional overlap beyond geometric proximity.
        "RAG document group" framing is unjustified.
```

### 10.3 KILL-NO-GROUP-OVERLAP

```
IF paired bootstrap 95% CI of:
  ReadReusePotential(real group) - ReadReusePotential(random control)
  contains 0
THEN: KILL
REASON: Real revision groups have no more overlap than random batches.
```

### 10.4 KILL-GENERIC-BATCH-REPACKAGING

```
IF existing-batch baseline (Greator-style or FreshDiskANN consolidation)
  achieves ≥ 90% of the benefit that any group-aware mechanism could add
  over Serial-group-cache
THEN: KILL
REASON: Existing batch mechanisms already capture the benefit.
        New mechanism would be repackaging.
```

### 10.5 FAIL-WORKLOAD-OR-TRACE-CLOSURE

```
IF I/O closure residual (after all explicit explanations) > 5% of total bytes
OR IF any trace field has >1% missing/null values
OR IF index fork hash verification fails for any condition
THEN: FAIL
REASON: Measurement infrastructure is not trustworthy.
```

### 10.6 Absolute-savings floor

```
IF median absolute savings (Serial-cold - Serial-group-cache)
  across all real groups < 5 SSD pages (20 KiB at 4 KiB pages)
  OR < 2 ms wall time
THEN: KILL (supplement to 10.1)
REASON: Even if relative overlap is high, absolute savings are too small
        to justify any mechanism complexity.
```

---

## 11. Confound Checks (Gate Section 8)

### 11.1 Page cache dominance (§8.1)
Covered by fail-stop 10.1. If Serial-group-cache ≈ Union-oracle, shared graph traversal is absent.

### 11.2 Geometry-only explanation (§8.2)
Covered by fail-stop 10.2. Control B isolates geometry from document identity.

### 11.3 Existing batch dominance (§8.3)
Covered by fail-stop 10.4. Must run Greator-style localized update as the "existing batch" baseline, not a strawman.

**IMPORTANT:** Claude's original design listed "Existing batch/buffered path: if system has public batch path, run it." This is too vague. The baseline MUST include Greator's mechanism (or equivalent): topology-aware scan → affected vertex identification → page-aware cache → ASNR repair. If DGAI/OdinANN don't have this natively, it must be implemented as a baseline before claiming novelty.

### 11.4 Sequential semantics (§8.4)
Record final graph digest and per-node adjacency differences for serial-cold vs serial-group-cache. They must be identical (same algorithm, only cache differs). If not, the cache is affecting correctness → FAIL.

### 11.5 Group-size artifact (§8.5)
Stratify all analyses by group size strata [2-5], [6-15], [16+]. Do not aggregate across strata. Report per-stratum.

### 11.6 Unchanged chunk inflation (§8.6)
Enforced by the content-hash exact matching in Section 4. Verify: no chunk with the same content hash appears in both the delete and insert sets of any group.

---

## 12. Overall Assessment

### Novelty concerns (elevated after primary-source audit)

Codex's primary-source verification reveals that the novelty gap is **narrower than Claude's report suggests**:

1. **Greator already has repair-target dedup + page I/O dedup** for small batches. Claude incorrectly described this system as "repairs one deletion at a time."
2. **FreshDiskANN consolidation already deduplicates** affected vertices across the batch.
3. **Slipstream's warm-start** would naturally apply to sequential document-group insertions.
4. **Control C design flaw**: Claude's proposed "shuffle old/new pairing" is ineffective because graph operations depend on which vectors are deleted/inserted, not on their pairing. Revised to use non-adjacent revision from the same document.

### What remains potentially novel

The only remaining novelty claim is:
> The a-priori-known document-revision group boundary, combined with the predictable delete-old/insert-new structure of revision updates, enables optimizations that existing batch mechanisms (which are group-agnostic) cannot exploit.

This is an empirical claim that A0 profiling can test. But the prior probability of survival is low:
- Greator's page-aware cache ΔG likely captures most page I/O overlap.
- Slipstream's warm-start likely captures most search-path overlap for insertions.
- FreshDiskANN consolidation already deduplicates repair for deletions.
- The residual after these mechanisms may be negligibly small.

### Verdict

**CONDITIONAL PROCEED-TO-PROFILING** with the following requirements:

1. **Mandatory Greator-equivalent baseline:** The "existing batch" baseline must implement Greator's core mechanisms (topology-aware affected-vertex identification, page-aware cache, ASNR). Without this, any measured benefit could be trivially explained by existing techniques.

2. **Slipstream warm-start baseline:** Add a fifth baseline condition: serial updates with Slipstream-style warm-starting for insertions within the group. This isolates the contribution of search-path sharing.

3. **Corrected Control C:** Use non-adjacent revision from same document, not shuffled pairing.

4. **DGAI/OdinANN instrumentation audit:** Before committing to A0, verify that the 7 instrumentation points (Section 8.1) exist or can be added within 1 day of engineering effort. If >3 hooks are missing, the trace closure requirement cannot be met → FAIL-WORKLOAD-OR-TRACE-CLOSURE.

5. **Estimated KILL probability: 70–75%** (higher than Claude's 60% estimate, due to Greator/Slipstream/FreshDiskANN mechanisms that Claude underestimated).

If all 4 requirements are met, profiling is worth the low cost (estimated 2 hours wall clock, 15 GiB NVMe). The direction has a clean empirical question even if the answer is likely negative.

---

## 13. Closure Pass 2：Research-Review and Local Artifact Audit

**Timestamp:** 2026-07-20 18:25:56 UTC+8

**Superseding prelaunch status:** **`RETURN-FOR-REVISION` / `NOT-PASS-PRELAUNCH`**

本节由 Codex 主审、一个两轮 independent senior review、一个 workload/statistics audit 和一个逐源码 trace audit 共同形成，覆盖并取代 Section 12 的 `CONDITIONAL PROCEED-TO-PROFILING`。Gpt gate 唯一允许的启动令牌是精确的 `PASS-PRELAUNCH`；当前没有该令牌，A0 不得运行。

### 13.1 Decisive blockers

1. **Frozen manifest 尚不存在。** Section 5 的 model revision、weights、binary/config/source hashes 和 seed 仍是占位符；三个 source 的 snapshot/range、Wikipedia page set、base corpus `N`、tokenizer revision、revision manifest、member order 和 active checkpoint 均未冻结。
2. **两个系统的 required trace 均未闭合。** 对实际 Atlas source 逐项审计后，DGAI 与 OdinANN 的 visited IDs、candidate IDs、read-page IDs、prune input/output、affected targets、modified pages、write submissions 均为 `OPEN`，即两者都是 `0/7 CLOSED`。存在局部变量或 aggregate counters 不等于能输出逐 update ID trace。
3. **强 baseline 不可执行。** Greator-equivalent localized repair/page cache 与 Slipstream warm-start 是不可省略的解释变量，但当前 frozen artifacts 不包含它们。未经新 gate 实现这些 baseline 会违反本轮“不修改 DGAI/OdinANN、不直接设计机制”的 stop line；不实现则 positive result 不能排除 generic batch/warm-start explanation。
4. **Workload/control generator 语义未闭合。** Hash set 会折叠重复 chunk，必须改为 occurrence-aware multiset matching；`commit~1:path` 未处理 merge parent、rename/add/delete；Control A/B 没有合法的 active-delete/inactive-insert pool；Control C 允许 2× size mismatch 并事后排除缺失样本，不能形成严格 paired quadruple。
5. **I/O closure invariant 写错。** `logical <= engine <= device` 不是普遍关系。application request、application-cache miss、engine submit、engine completion、cgroup block bytes 和 whole-device delta 必须分别命名、用 event identity 对账；`io.stat` 不是 NAND bytes，`/sys/block` 还会混入其他进程。
6. **资源估算漏项并违反 8-hour cap。** 当前设计为 600 real groups、4 group types、2 chunkers、2 embedders、2 systems，得到 19,200 个 group-config tuples；加入 serial-cold、serial-group-cache、existing-batch 和 warm-start 四个可执行条件后是 **76,800 executions**，另有 19,200 条 derived union-oracle records。即使错误地假设每次仅 1 秒，执行也需 21 小时 20 分，未计 clone/reset/hash、cache discipline、query interference、repetition 和 embedding。
7. **统计 classifier 未闭合。** “CI contains zero”不能证明等价；85%、90%、5 pages、2 ms、80% groups 均未从 measurement resolution、bookkeeping overhead 或 minimum practical effect 推导。必须冻结 document-clustered paired unit、seed/reps、equivalence margin、多重比较、label precedence，并直接实现 gate 的 `LCB(real benefit over controls) > UCB(overhead)`。
8. **Quality/visibility protocol 缺失。** Foreground query set、ground truth、Recall、QPS/p99、query/update concurrency、repetitions、drain/quiescence 和 fresh-process visibility 尚未定义。

### 13.2 Local source and trace inventory

| System | Source identity | Current state | Required trace hooks |
|---|---|---|---:|
| DGAI | `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/src/DGAI-clean`, HEAD `a0179b876a4bd453336dc2893b46ae890f680555` | dirty; tracked diff SHA-256 `2944097ca80293205aa550ee7ded170934c59895b28c6d954c6b3ee9c79977c3`; binary SHA-256 `dc001aff1a879ae95255d015777a40dd4f52d9bd591fe3b31105a5a99399dc94` | `0/7 CLOSED` |
| OdinANN | `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/src/OdinANN-PipeANN`, HEAD `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b` | dirty; tracked diff SHA-256 `b070c42967e053c7b4d2c7184fe5fc63ea72e2aa9d7a4e4de0712f4845d2374a`; binary SHA-256 `70b175f26eab7c95bf0ff2c75afc096ac5c85ff149c617a85a8baf9db97f82e1` | `0/7 CLOSED` |
| older DGAI `PROFILE_RMW` tree | `/home/ubuntu/pz/VectorDB/repos/DGAI` | aggregate counts + partial page events; no complete per-update IDs | at best `2/7 CLOSED` |

OdinANN 的目录名 `build/OdinANN-uring` 不能作为 engine provenance：当前 CMake cache 实际为 `IO_ENGINE=aio`。旧 DGAI profile 还把 cache filtering 前的逻辑 reads 与真正提交的 disk reads 混在一起。现有 page cache 是单 update 生命周期的 transient/ref-counted cache，不是跨 update 的 `Serial-group-cache`。现有 W1 drivers 也不满足 frozen serial semantics：DGAI 使用 insert→delete 并 merge/reload，OdinANN 使用并发 insert/delete。

数据盘为 `/dev/nvme8n1` 上的 ext4，当前约 760 GiB 可用；系统盘约 148 GiB 可用。正式 index/trace 只能写入项目数据盘。ext4 不能被假设提供 reflink clone，因此每 group/condition 的 reset/copy 成本必须实测或改成经过审阅的 snapshot strategy，不能沿用 15 GiB/2 hour 猜测。

### 13.3 Required generator corrections

- source 必须固定为三个具体 repository/corpus 和不可变 snapshot，不保留 `rust-lang/book or python/cpython` fallback；
- Git revision 使用明确的 first-parent/merge policy，跟踪 rename/add/delete，且在 trace 前冻结 inclusion/exclusion；
- unchanged matching 使用 `Counter<(sha256, occurrence)>`，按 `min(old_count,new_count)` 匹配，并明确 hash 输入是 raw bytes 还是预注册 canonical bytes；
- 每个 revision 绑定 pre-revision active checkpoint，保证 delete members 已存在、insert members 尚不存在；
- A/B/C controls 必须与 real group 在同一 checkpoint 匹配 delete/insert counts、group size、length distribution；B 再匹配明确的 geometry statistic/caliper并要求 cross-document；
- 只在 real/A/B/C 全部成功的共同样本上做 paired inference，失败规则和 tie-break 在看 trace 前冻结。

### 13.4 Research-review loop record

Independent reviewer ID：`/root/rag_group_prelaunch_reviewer`。

- **Round 1:** 发现启动标签、frozen inputs、trace hooks、baseline authorization、I/O invariant、run math、multiset lineage、controls、active checkpoint 与 statistics 十类 blocker，建议 `RETURN-FOR-REVISION`。
- **Round 2:** 专门审查“只用现有 frozen artifacts 是否可 PASS”。结论是不存在诚实的 PASS 路径：serial/cache/union 只能证伪 overlap/cache 动机，不能证明 state-of-the-art batch/warm-start 后仍有 residual opportunity。
- **Consensus:** Greator 与 Slipstream 是不可省略的解释变量；除非 Gpt 授权强 baseline/trace implementation，或把 A0 改成只允许负裁决的 trace-only gate，否则不得签发 `PASS-PRELAUNCH`。

### 13.5 Two routes requiring Gpt decision

**Route A — strong-baseline preflight amendment**

另行授权一个 instrumentation/baseline gate，范围仅包括：补齐 DGAI/OdinANN 七类 trace；实现并验证 application-level group cache；导入或等价复现 Greator 与 Slipstream baseline；冻结可执行 manifest；用小于正式 A0 的 canary 实测单 run time、trace bytes、clone/reset cost 和 semantic equality。完成后重新审查 prelaunch。

**Route B — negative-only trace gate**

不实现强 baseline，仅测 serial/native-cache/native-existing-batch/union phenomenon。该路线的 positive outcome 最多可进入 `HOLD-NEEDS-STRONG-BASELINE`，不能输出 `PASS-DOCUMENT-GROUP-OVERLAP` 或进入机制设计；negative outcome 可以按现有 labels KILL。因为现有 final-label 列表没有该 HOLD 标签，Route B 也需要 Gpt 修改 gate。

### 13.6 Final prelaunch verdict

```text
RETURN-FOR-REVISION
NOT-PASS-PRELAUNCH
A0_NOT_AUTHORIZED
```

若必须映射到现有 A0 final labels，当前证据状态对应 `FAIL-WORKLOAD-OR-TRACE-CLOSURE`，但这不是已运行 A0 的结果。本轮不下载 corpus/model、不实现 hook/baseline、不构建索引、不运行 profiling。
