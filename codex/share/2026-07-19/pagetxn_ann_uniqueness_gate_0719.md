# PageTxn-ANN paper-only uniqueness gate

## 0. Registered question and verdict

**Question.** Does crash recovery for an on-disk graph ANN index admit an ANN-specific, query-safe partial-update invariant that a fair generic WAL/MVCC/COW design cannot provide at comparable granularity and cost?

**Verdict: `KILL-GENERIC-TRANSACTION-PACKAGING`.**

The local systems contain a real durability defect and several multi-page crash windows. That fact supports an engineering problem, but not the registered novelty claim. Every currently specified safe publication state is expressible as a logical/physiological WAL subtransaction, MVCC visibility transition, or COW root/manifest swap. The one graph-aware candidate—keeping a deleted vertex traversable while excluding it from results and installing bypass edges before reclamation—is a useful lazy-delete policy, but its durable commit is a one-record logical transaction and its “add-only repair is safe” premise fails for finite-candidate/finite-budget graph search. No local, efficiently checkable ANN invariant was found that both bounds post-crash query quality and yields a non-constant recovery/write-ordering separation over those baselines.

This is a paper-only decision. No PageTxn implementation, fault injection, or performance experiment was run.

## 1. Fair failure model and baselines

### 1.1 Failure model

The gate assumes an ordinary NVMe/block-device environment, not ZNS or persistent memory:

1. the application updates 4 KiB index pages, but power-loss atomicity is not assumed above the device's documented atomic unit;
2. page writes may tear, persist out of submission order, or remain in volatile caches until an explicit durability barrier;
3. a crash may occur after any write or barrier and may recur during recovery;
4. recovery must be idempotent and must distinguish corrupted/torn records using length, version/LSN, transaction or operation ID, and checksum;
5. concurrent queries may observe only explicitly published states; latches alone are not a crash protocol.

### 1.2 Baselines that the proposal must beat

The comparison is not a single monolithic “log every final page” strawman.

* **Logical/physiological WAL:** log operation intent or changed records, obey WAL-before-data, use transaction/operation ID plus pageLSN, append a commit marker, redo committed work, ignore or undo uncommitted work, and use group commit.
* **Phased WAL:** expose a sequence of independently query-safe subtransactions; defer recomputable graph maintenance and replay it from logical intent.
* **MVCC/epoch publication:** prepare new records privately, then publish visibility with a small durable metadata transition; readers continue on the old version until publication.
* **COW/shadow state:** write new pages out of place and atomically switch a root/manifest/version pointer; use structural sharing where possible.

An ANN-specific protocol need not have identical constants to these baselines. To pass, however, it must identify a graph/query invariant unavailable to them at comparable granularity and show an asymptotic, non-constant, or otherwise material lower-bound separation. No such separation is presently established.

## 2. The local defect is real

### 2.1 Durability mechanism is absent

In DGAI, `repos/DGAI/include/v2/journal.h:15-61` defines a journal interface, but its database open, append, checkpoint, and `SyncWAL` bodies are commented out. Calls to the object therefore do not establish durable transactions. The aligned file writer submits and waits for writes, but the audited path has no `fsync`, `fdatasync`, durable commit record, or atomic manifest rename.

### 2.2 Coupled insertion spans multiple records/pages

`repos/DGAI/src/update/direct_insert.cpp` performs, in order:

1. ID/PQ allocation and candidate search/pruning (`28-93`);
2. target and neighbor-location allocation plus page reads (`104-194`);
3. target record/tag creation and neighbor reverse-edge modification, including possible whole-record relocation (`212-299`);
4. cache/map publication (`307-328`);
5. page writes (`339-380`).

With `BG_IO_THREAD`, cache/location state may become visible before the queued writes complete (`340-353`, `387-416`). A crash can therefore leave a target without all incoming edges, some reverse edges pointing at stale locations, or volatile mappings ahead of durable pages.

### 2.3 Decoupled insertion and deletion have still larger write sets

`repos/DGAI/src/update/direct_to_topo_insert.cpp` separates coordinate and topology persistence. It publishes mappings/PQ/tag state before disk completion (`246-314`), writes target coordinates (`553-607`), writes/splits/repackages target topology (`618-908`), and later applies reverse-topology writes (`911-1018`). There is no durable commit boundary tying these phases together.

Deletion is already lazy in memory: the query may traverse a deleted node while filtering it from final results. Triggered deletion then clears the deleted node, repairs incoming edges in batches, writes those batches, and changes medoid/metadata later. A crash can leave a mixed graph. This motivates the strongest candidate below, but does not by itself establish novelty.

## 3. What “query-safe” could mean

The word is ambiguous unless its contract is fixed.

| Contract after crash | What it guarantees | Assessment |
|---|---|---|
| byte/structural safety | pages parse; IDs and checksums are valid | generic WAL/COW |
| transaction visibility | a query sees one committed logical version | generic WAL/MVCC |
| graph reachability | every live vertex remains reachable from an entry | graph-aware, but too weak for bounded ANN search |
| fixed-algorithm ANN safety | for a declared query domain, metric, candidate-list/expansion budget and approximation/recall target, recovery states preserve a bound | potentially ANN-specific; no valid local invariant found |

Only the fourth contract could support `PASS-ANN-SPECIFIC-INVARIANT`. Merely preserving a directed path, degree bound, or parseable adjacency list does not control which paths a finite-list, finite-budget search explores.

## 4. Candidate invariants and why they do not pass

### 4.1 Prepared-before-visible insertion

A natural protocol writes the new vector and outgoing adjacency privately, installs one or more incoming anchors, publishes the new ID, and repairs reverse edges lazily.

This is functionally a generic prepare/publish protocol: MVCC or COW can retain the old graph, while logical WAL records the new node and a small publish transition. One incoming anchor proves at most reachability. It does not bound recall under a finite candidate list or expansion budget because the anchor path may be evicted or delayed by closer-looking dead ends. Logging a compact insertion intent and recomputing reverse-edge repair also defeats any assumed need to log all final pages.

### 4.2 Traversable tombstone plus monotone bypass repair

The most credible local object is:

1. durably mark deleted vertex `x` as result-invisible but traversal-visible;
2. retain `x` and its old edges as navigation state;
3. add bypass edges before removing old edges;
4. reclaim `x` only after a certificate says removal is safe.

Steps 1–2 can give clean logical-delete semantics, and the current search path already resembles this policy. But the durability action is a one-record logical transaction followed by deferred maintenance—the standard WAL/MVCC baseline can express it directly. It is therefore an application policy, not yet a new recovery mechanism.

Step 3 does not make bounded search quality monotone. The relevant bound in DiskANN-style search is the retained candidate-list capacity `L` (and, separately, the expansion/I/O budget), not merely the number of nodes expanded in one iteration. Consider a deletion repair for traversal-visible vertex `x`. Before repair:

```text
old graph: s -> x; x -> {t, z_1, ..., z_L}
d(t,q)=0, d(z_i,q)<d(x,q)<d(s,q), and every z_i is a dead end
```

In the old graph, expanding `s` first exposes only `x`; expanding `x` then exposes exact neighbor `t`. Now let a crash-visible, add-only bypass phase have persisted `s -> z_1,...,s -> z_L` but not yet `s -> t`, while retaining `s -> x` and all old edges. After expanding `s`, the `L` closer-looking distractors can fill the retained list and evict `x`, so `t` is never exposed. The graph is a strict edge superset and old reachability is intact, yet the fixed finite-list search loses the nearest result. The same phenomenon can be constructed against a fixed expansion/I/O budget by making the newly exposed distractors consume that budget.

For a graph with maximum degree `R`, this direct construction takes `L <= R`; the fixed expansion/I/O-budget variant covers other finite-resource settings. A particular implementation may have a larger `L`, another stopping rule, or batch publication, so this counterexample refutes an **unconditional** edge-addition/partial-bypass monotonicity claim rather than asserting that every edge addition hurts every query. Batch-atomic publication returns to WAL/MVCC/COW; a positive weaker protocol must bind the exact search, candidate retention, publication unit, and stopping semantics.

Step 4 is the missing research object. A local degree/reachability check is insufficient; a certificate must quantify finite-budget navigability over a declared query domain. No such certificate is present in DGAI/OdinANN or established here.

### 4.3 Recovery by exploiting graph redundancy

Skipping redo when another path exists sounds ANN-specific, but verifying a path is a generic directed-connectivity property and still says nothing about finite-list/finite-budget behavior. A recovery-time spanning arborescence or edge-disjoint-path condition would likewise be a generic graph certificate. If omitted repair is recomputable, logical WAL can record intent and defer the same repair; if it is not recomputable, the specialized scheme must persist equivalent information somewhere.

### 4.4 Smaller atomic unit

The smallest useful semantic transactions identified here are:

* insert: private vector/outgoing list plus visibility publication;
* delete: durable traversal-visible/result-invisible tombstone;
* repair: independently committed edge/batch update;
* reclaim: removal after a separately verified safety condition.

These units are smaller than “atomically replace every touched page,” but they are also exactly the units a logical WAL or MVCC implementation can commit. Granularity alone is not a separation.

## 5. Formal observations and counterexamples

### Observation 1: phase encoding

Let a proposed PageTxn protocol be a finite state machine whose crash-visible states are `S0,...,Sk`, and suppose every transition publishes enough durable information to identify or reconstruct the next safe state. A logical WAL can record each published transition as a subtransaction, keep uncommitted state invisible, and redo committed transitions idempotently. It can therefore reproduce the same public state language.

This is an expressiveness observation, not a claim of identical byte constants. It means that a paper must prove a cost separation rather than treating “partial update” itself as outside WAL.

### Observation 2: missing reverse edges invalidate naive publication

Suppose new vertex `v` and its outgoing list are durable and visible, but all incoming reverse edges to `v` are absent. For query `q=v`, a graph search starting at the old entry cannot reach `v`; the exact nearest neighbor is therefore missed. Adding one incoming edge prevents this particular disconnection but does not prevent that path from being evicted or left unexpanded under finite search resources.

### Observation 3: reachability is not recall monotonicity

The finite-candidate-list construction in Section 4.2 proves that retaining every old edge while partially adding predecessor-to-successor bypass edges can reduce result quality: newly exposed distractors evict the old gateway before its best successor is discovered. Thus neither edge-superset monotonicity nor entry reachability is a sufficient crash invariant for ANN.

### Observation 4: deletion ordering has the dual problem

For `s -> a -> b`, making `a` non-traversable before adding a replacement path disconnects `b`. Adding replacement edges first avoids that structural failure, but under a bounded degree it may require page replacement/COW, and under finite candidate/expansion resources the new alternatives can still change retention and stopping decisions. The order is operationally sensible but does not supply the required quality theorem.

## 6. Nearest-work and baseline audit

| Work/system | Relevant fact | Consequence for PageTxn novelty |
|---|---|---|
| ARIES, Mohan et al., TODS 1992 | physiological WAL, recovery, fine-grained transactional updates | generic recovery baseline must include logical/physiological logging, not full-page-only WAL |
| [Dynamicity and Durability in Scalable Visual Instance Search](https://arxiv.org/abs/1805.10942), Lejsek et al., 2019 | a transactional disk-based high-dimensional NV-tree with ACID, standard WAL, checkpoints, undo/redo/reinsertion recovery, evaluated to 28.5B vectors | directly invalidates a broad “first durable/transactional high-dimensional index” claim and shows standard WAL packaging in this domain |
| [RECIPE](https://arxiv.org/abs/1909.13670), SOSP 2019 | converts concurrent indexes to crash-consistent persistent-memory indexes using structural conditions and small changes | index-specific partial-update reasoning is established prior art, although its medium is PM rather than NVMe |
| [MOD](https://arxiv.org/abs/1908.11850), 2019 | out-of-place updates, structural sharing and shadow-style atomic publication | fair comparison must include COW/shadow alternatives, not just in-place WAL |
| [P-HNSW](https://doi.org/10.3390/app151910554), Lee et al., 2025 | crash-consistent HNSW on persistent memory; Node Log and Neighbor List Log use `NONE/LOGGING/LOGGED`, with `N_COMPLETE` additionally used only by Node Log, to recover partial new-node out-edge and neighbor in-edge updates, including crash during recovery | direct graph-ANN precedent for phase-state logging and graph-aware recovery; different medium, but strongly narrows any PageTxn mechanism claim |
| [Qdrant Storage / Versioning](https://qdrant.tech/documentation/manage-data/storage/) | production vector DB writes changes to a sequence-numbered WAL before applying them and restores after abnormal shutdown | durable vector-system WAL is production practice; this does not by itself prove graph-page atomicity |

The earlier audit incorrectly conflated P-HNSW with similarly named PCA-based filtering work. The official P-HNSW paper was published in *Applied Sciences* 15(19):10554 on 29 September 2025 and directly addresses crash-consistent HNSW. Its PM/cache-line persistence model differs from this gate's ordinary-NVMe page model, so it does not automatically solve the target system; nevertheless, its node/neighbor logging and phase recovery invalidate any claim that graph-aware partial-edge recovery is itself new. Failure to locate an exact disk-graph-ANN counterpart would not prove universal absence, and the mechanism is already covered both by this direct graph precedent and by the generic baselines above.

## 7. The object that would have been needed for PASS

A salvage would require something like a **robust query-navigability certificate**. For declared search algorithm `A`, candidate-list/expansion budget `B`, query domain `Q`, approximation factor `alpha` or recall target `r`, and crash-visible graph states `G_i`, it would have to establish

```text
for every q in Q, every allowed crash state G_i,
A(G_i, q, B) satisfies the registered alpha/recall guarantee,
```

while being local or incrementally maintainable, surviving the update phases, and reducing persisted information or ordering barriers beyond logical WAL/MVCC/COW by a proved non-constant or material amount.

Ordinary reachability, reverse-edge completion, degree bounds, edge supersets, and traversable tombstones do not imply this statement. No theorem connecting Vamana/HNSW robustness to such all-crash-state finite-resource safety was supplied or derived. If such a theorem were found, the primary contribution would be a new navigability/robustness theorem; PageTxn would be one system application.

## 8. Decision boundary

### Supported

* DGAI/OdinANN-style dynamic disk graphs have genuine durability and publication-order defects worth fixing in an engineering system.
* A practical design can reduce the synchronous commit unit with logical insert/delete intents, prepared-before-visible publication, traversable tombstones, and deferred repair.
* Fault injection and recovery testing would be valuable engineering validation after choosing to build such a system.

### Not supported

* an ANN-specific crash invariant unavailable to generic WAL/MVCC/COW;
* a query-quality guarantee for partial graph states;
* lower log volume, fewer barriers, or faster commit by theorem relative to a fair logical baseline;
* a first durable/transactional high-dimensional index claim;
* authorization to implement or benchmark PageTxn as a research candidate.

Accordingly the only defensible registered outcome is:

```text
KILL-GENERIC-TRANSACTION-PACKAGING
```

Per the direction tree, the next step is Case E: problem discovery anchored in measured pathologies on the available ordinary-NVMe environment, while excluding the already exhausted mechanism axes. This report does not start that step.

## 9. Reproduction anchors

Local source anchors:

```text
/home/ubuntu/pz/VectorDB/repos/DGAI/include/v2/journal.h
/home/ubuntu/pz/VectorDB/repos/DGAI/src/update/direct_insert.cpp
/home/ubuntu/pz/VectorDB/repos/DGAI/src/update/direct_to_topo_insert.cpp
/home/ubuntu/pz/VectorDB/repos/DGAI/src/utils/linux_aligned_file_reader.cpp
```

Downloaded full-text audit copy:

```text
/tmp/pagetxn_papers/txn_nvtree.txt
/tmp/phnsw.txt
```

Useful checks:

```bash
rg -n 'append|checkpoint|SyncWAL' repos/DGAI/include/v2/journal.h
rg -n 'fsync|fdatasync|syncfs|rename' repos/DGAI/src repos/DGAI/include
rg -n 'write-ahead|checkpoint|committed|recovery' /tmp/pagetxn_papers/txn_nvtree.txt
```

## 10. Independent adversarial review

The first adversarial review returned `REVISE`, not automatic acceptance. It found three material issues: the nearest-work audit had missed the real 2025 P-HNSW paper; the original beam-width-1 example conflated per-iteration expansion width with DiskANN's retained candidate-list capacity; and one local source path plus the Qdrant documentation URL were stale. Sections 4.2, 5, 6, and 9 incorporate those corrections.

The strongest attempted salvage was a **routing-stable tombstone**: a deleted vertex retains its old adjacency and remains traversal-visible, while a durable bit makes it result-invisible; search may expand its candidate pool until it obtains `k` live results. This is genuinely ANN-specific query semantics, and local DGAI partially implements the two visibility roles. It still does not separate the durability protocol: a logical WAL or MVCC delete record can publish the same state at comparable granularity, and repair can be regenerated from the intent plus old adjacency. If bypass edges become visible one by one, the corrected finite-`L` counterexample defeats unconditional recall monotonicity; if a complete bypass set is published atomically, the protocol returns to generic WAL/MVCC/COW publication.

After correction, the review's substantive conclusion is unchanged: no ANN-specific durability invariant with a proved cost separation over fair logical WAL/MVCC/COW remains.

**Post-correction verdict: `ACCEPT` (minor precision edits incorporated).**
