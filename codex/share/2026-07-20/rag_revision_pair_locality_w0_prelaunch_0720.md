# RAG Document Revision：Paired-Replacement Locality W0 Prelaunch

> **Amendment status (2026-07-20):** GPT's later amendment supersedes the
> ordinal/occurrence pairing text in Sections 3.2, 4.1, and Control C below.
> The implemented rule and final artifact closure are recorded in Section 13,
> which also supersedes all earlier `OPEN`/review-request state:
> stable exact-payload LCS anchors, with only unmatched `1 -> 1` spans admitted.

**Date:** 2026-07-20（UTC+8）  
**Owner:** Codex  
**Upstream gate:** `gpt/share/2026-07-20/rag_revision_pair_locality_w0_gate_0720.md`  
**Current state:** `FAIL-W0-WORKLOAD-CLOSURE`
**Execution authorized:** `false`

## 0. Boundary and current verdict

Broad Document-Group Update A0 remains stopped. This prelaunch covers only the workload-level question:

> 对真实文档修改形成的 old chunk→new chunk pair，旧向量是否是新向量的有效结构锚点，其局部邻域是否显著覆盖新向量的目标邻域？

No DGAI/OdinANN modification, graph trace hook, Greator/Slipstream implementation, update-in-place, old-adjacency reuse, NVMe profiling, or broad group batching is included.

The immutable repository ranges and remote model artifacts are now bound. The final pair/background manifests, Nomic CPU canary, runner/config hashes, and exact-top-k tests are not yet materialized. Therefore this document deliberately does **not** issue the run gate token and no measurement has started.

## 1. Claim map

| ID | Claim / anti-claim | Minimum convincing evidence |
|---|---|---|
| C1 | A real adjacent old revision is a useful structural anchor for its new revision. | Against random cross-document anchors, corrected lower confidence bounds are positive across both sources, both models, and at least two of `R={16,32,64}` for neighborhood inheritance and matched-budget candidate efficiency. |
| C2 | Temporal lineage adds information beyond static geometric proximity. | Real adjacent anchors also beat distance-matched cross-document anchors and non-adjacent same-section versions under the same replication rule. |
| A1 | Any apparent benefit is only semantic proximity. | If real beats random but not distance-matched controls, emit only the geometric-replacement label. |
| A2 | Any apparent temporal benefit is not specific to adjacent revisions. | If non-adjacent same-section history performs as well, emit the no-temporal-lineage label. |

This W0 is a necessary-condition workload test, not an ANN performance result.

## 2. Immutable source snapshots and range

All acquisition and future materialization live under:

```text
/home/ubuntu/pz/VectorDB/data/VectorDB/rag_revision_pair_locality_w0
```

The metadata-only Git clones currently consume 302 MiB on `/dev/nvme8n1`; no experiment data was written to the system volume.

### 2.1 Frozen Git provenance

| Source | Exact URL | Acquired remote tip | Range lower bound `lo` (excluded) | Background/range upper bound `hi` (included) | `hi` tree |
|---|---|---|---|---|---|
| Kubernetes | `https://github.com/kubernetes/website.git` | `d19aacebe8061a6ef5dcc1e68904aaefe35c5445` | `7b11b1626a8fd9a64a6237e8ca9033a09aed1845` | `a01d6f3f0487860b12c47fe9953606db9508e3f9` | `46137952d52210b7af1aa1b646dce054d4f25487` |
| CPython | `https://github.com/python/cpython.git` | `e0293b0de4071ca591e36fd42ef04285b91ef546` | `c5438fdf4706a70bdd19338edc000dacffff6837` | `c4ab024530feb3a66d51bcef2e33b309ca0d543f` | `7b74bcc72fe854c97dbbf42cd7517a4bc8610b2d` |

The range is the completed calendar year 2025, frozen as exact full SHAs rather than date aliases. Enumeration is exactly:

```text
git rev-list --first-parent --reverse lo..hi
```

| Source | First-parent commits in range | SHA-256 of newline-delimited ordered commit SHAs |
|---|---:|---|
| Kubernetes | 2,655 | `1b17ffedfab5f47e9a78737e912a8f0f455a3fe4ba666f7c14191813bc8dcdc5` |
| CPython | 4,771 | `c653df138cd38bfcce68cc605a85e3b0feeae3a9b1ee4a642e5e82ce929998a5` |

### 2.2 First-parent, rename, add/delete policy

For each child commit `c` on the frozen spine:

1. `p = c^1`; root commits are excluded. Merge commits are retained and compared only with their first parent, because Kubernetes primarily lands documentation changes through merge commits.
2. Diff command semantics are `git diff-tree -r --no-commit-id --name-status -M100% p c`.
3. A revision is eligible only when exactly one eligible documentation path has status `M` and the path is identical on both sides.
4. Eligible-path `A`, `D`, `R`, `C`, or `T` records exclude the revision. A rename with edits that appears as `D+A` under `-M100%` is also excluded.
5. Changes to non-eligible paths do not exclude the commit.
6. Every exclusion receives a frozen reason code; there is no manual rescue or post-metric inclusion.

### 2.3 Path and blob inclusion

| Source | Include regex | Required Git mode | Content rules |
|---|---|---|---|
| Kubernetes | `^content/en/docs/(?:.*/)?[^/]+\.md$` | regular blob `100644` | strict UTF-8, raw size `256..524288` bytes |
| CPython | `^Doc/(?:.*/)?[^/]+\.rst$` | regular blob `100644` | strict UTF-8, raw size `256..524288` bytes |

There is no discretionary semantic-directory exclusion. Symlinks, submodules, invalid UTF-8, and out-of-cap blobs are excluded with explicit reason codes.

At each `hi`, the path-candidate tree manifest is the raw `git ls-tree -r hi -- <root>` output filtered by the exact regex, preserving byte order:

| Source | Candidate files | Path-candidate manifest SHA-256 |
|---|---:|---|
| Kubernetes | 1,565 | `5862853f9948a0d74aac629d369bc60e32f7fa16f964f97c45a6d73e733dda83` |
| CPython | 537 | `96710f182ce643b8312966c178cbf92cdc89dea2b4bee58e454abf745b2c34fc` |

The final decoded inclusion/exclusion manifest is still OPEN until source blobs are materialized after review.

## 3. One deterministic structure-aware chunker

Both formats use one `heading-aware-v1` chunker with format-specific heading recognition and one common canonicalization/packing path.

### 3.1 Canonical document and section identity

- Document path: repository-relative POSIX path; `.` and `..` are forbidden; no case folding.
- Markdown headings: ATX and Setext headings outside fenced code blocks. Initial YAML front matter is metadata, not body text.
- reStructuredText headings: paired overline/underline or underline-only adornments; adornment level is assigned by first appearance within the document.
- Heading text normalization: Unicode NFC → trim → collapse Unicode whitespace to one ASCII space → Unicode casefold.
- Section path: normalized heading stack joined by `/`; pre-heading content uses the literal sentinel `<root>`.
- Canonical body: strict UTF-8; CRLF/CR → LF; trailing SP/TAB stripped per line; leading/trailing blank lines stripped; runs above two blank lines collapsed to two; all other Unicode code points preserved.

### 3.2 Packing and occurrence

- The chunk-length tokenizer is the pinned MiniLM **fast** tokenizer in Section 5, always called with `add_special_tokens=false` for length checks.
- The breadcrumb bytes are exact: `"[SECTION] " + " > ".join(normalized_heading_components)`; root content uses `"[SECTION] <root>"`. Components are the normalized strings from Section 3.1, not source markup or original capitalization.
- Split the canonical section body on runs of two or more LF characters into non-empty paragraph records. Each paragraph is a chunk; paragraphs are never repacked together and overlap is zero. An empty section emits no chunk.
- Exact embedding payload is `breadcrumb + "\n\n" + paragraph_part`.
- If a paragraph payload exceeds 254 MiniLM tokens, tokenize the remaining paragraph with offsets. Let `b` be the largest token prefix that may fit after the fixed breadcrumb and separator. Cut the original Unicode string at the start-character offset of token `b+1`, retaining intervening whitespace in the preceding part; re-tokenize the complete payload and decrement the cut one token boundary at a time until it is at most 254 tokens. Continue from the exact cut character with no strip/normalization. If the first tokenizer offset makes no progress, cut after one Unicode scalar and require the payload to fit or exclude as `UNSPLITTABLE_OVER_CAP`.
- The complete payload must contain at most 254 tokens before MiniLM adds `[CLS]` and `[SEP]`. A breadcrumb that alone exceeds 254 tokens is excluded as `HEADING_OVER_CAP`.
- `occurrence` is the zero-based document-order index among emitted chunks with the same normalized section path. It is never deduplicated.
- Full identity is exactly `(document_path, normalized_section_path, occurrence)`.
- `payload_sha256` hashes the complete UTF-8 embedding payload, including the visible breadcrumb. Same identity and same payload hash: unchanged, exclude.
- Same identity and different payload hash: one real `old→new` pair.
- One-sided identity: addition/deletion, exclude.
- No embedding-similarity realignment, learned threshold, or manual pairing is allowed.

`canonical_chunk_id` is `SHA256(canonical_json([source, document_path, normalized_section_path, occurrence, payload_sha256]))`, where canonical JSON is UTF-8, compact separators, no ASCII escaping, and a trailing LF. All compound hash inputs in this experiment use canonical JSON arrays rather than delimiter concatenation.

Fixtures must cover repeated headings, repeated equal chunks, heading rename/case change, an insertion before an occurrence, Markdown fences, RST directives, CRLF, malformed UTF-8, root content, empty sections, heading-budget overflow, multibyte Unicode at an offset boundary, and an over-cap no-whitespace token. Fixture hashes and runner source hash are OPEN before implementation.

## 4. Pair sampling and fixed background

### 4.1 Master seed and pair cap

```text
seed_text   = rag-revision-pair-locality-w0-2026-07-20
seed_sha256 = 527050c04eec3dd2c10e9865af170e2e7946582c3934909ab8d91baebfe6bb74
```

Frozen ID schema:

```text
seed = master_seed = the 64-character lowercase ASCII seed_sha256 string
source = exactly "kubernetes_website" or "cpython_doc"
pair_id = SHA256(canonical_json([
  source,
  parent_commit_full_sha,
  child_commit_full_sha,
  document_path,
  normalized_section_path,
  occurrence,
  old_payload_sha256,
  new_payload_sha256
]))
candidate_id = canonical_chunk_id (64-character lowercase ASCII hex)
```

Pair selection occurs before embeddings:

1. Generate every deterministic modified pair in the frozen range.
2. Within each document, rank pairs by `SHA256(canonical_json([seed, pair_id]))` and retain at most four.
3. Rank documents by the minimum retained pair key and retain at most 256 documents per source.
4. Thus the hard cap is 1,024 real pairs per source.

Each primary comparison must retain at least 64 distinct document clusters and 128 complete pairs per source. Otherwise stop before metric inspection with `FAIL-W0-WORKLOAD-CLOSURE`.

### 4.2 Common exact background

- Background checkpoint is the source-specific frozen `hi` commit.
- First remove every checkpoint chunk whose payload hash equals any selected real pair member or selected Control-C anchor.
- Rank remaining chunks by `SHA256(canonical_json([seed, source, canonical_chunk_id, payload_sha256]))`.
- Require at least 8,448 eligible chunks after exclusion. The first 8,192 are the core background and the next 256 are the ordered reserve. There is no smaller-N fallback.
- Both embedding models use exactly the same ordered background membership.
- A real or Control-C anchor is outside the core by construction. For a Control-A/B anchor `z` selected from the core, define the **comparison background** as `B_z = core - {z} + {first eligible reserve item}`. Both sides of that paired comparison are recomputed on the same `B_z`: real anchor versus A uses `B_zA`, and real anchor versus B uses `B_zB`. Real metrics from the unmodified core must not be reused for A/B comparisons. Control C and its real side share the unmodified core because both historical anchors were globally excluded. Thus every compared side has exactly 8,192 identical background vertices and neither anchor nor target is a background vertex.

To reconstruct every leave-one-anchor-out graph exactly without recomputing an all-pairs graph, the oracle exhaustively computes top-321 over the ordered 8,448-item universe. Filtering a row to the pair-specific 8,192-item membership and taking its first 64 entries is exact: at most 256 nonmember reserve items plus one excluded core anchor can precede the required 64 members.

The final pair, exclusion, core, reserve, and pair-specific membership manifests are OPEN until source materialization; each will be canonical JSONL sorted by `(source, commit_order, path, section_path, occurrence)` and SHA-256 hashed.

## 5. Frozen embeddings

### 5.1 Model artifacts

| Field | MiniLM | Nomic |
|---|---|---|
| Repository | `sentence-transformers/all-MiniLM-L6-v2` | `nomic-ai/nomic-embed-text-v1.5` |
| Revision | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | `e9b6763023c676ca8431644204f50c2b100d9aab` |
| `model.safetensors` SHA-256 / bytes | `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` / 90,868,376 | `9e7d262b1fe5ea350782829496efa831901b77486bbde1cea54a4c822d010d5c` / 546,938,168 |
| `tokenizer.json` SHA-256 | `be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037` | `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66` |
| `tokenizer_config.json` SHA-256 | `acb92769e8195aabd29b7b2137a9e6d6e25c476a4f15aa4355c233426c61576b` | `d7e0000bcc80134debd2222220427e6bf5fa20a669f40a0d0d1409cc18e0a9bc` |
| `special_tokens_map.json` SHA-256 | `303df45a03609e4ead04bc3dc1536d0ab19b5358db685b6f3da123d05ec200e3` | `5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a` |
| `vocab.txt` SHA-256 | `07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3` | `07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3` |
| Git tree-manifest SHA-256 | `581fa1a7181a015311a62704a1051a07ee2f03bdc2dddafec25bc0d7c91df7ef` | `998c1ce54a7896d3027fcfbdcdcbc9f941fcab1f46e10a0f015f7c37f3102de0` |

Nomic remote code is independently pinned:

```text
repo: nomic-ai/nomic-bert-2048
revision: 7710840340a098cfb869c4f65e87cf2b1b70caca
configuration_hf_nomic_bert.py sha256: f7871694b8de3d3df4ac6640313d5799ce323261a0fb90c5cc567ecc34a0039e
modeling_hf_nomic_bert.py sha256: 3b24a366c4cc31b869466ccfb7bbb8879e138c97f8de06c83d4fa1e31a21f149
tree-manifest sha256: 2165148a894982fba647ca28fba57979c7a5d6987b15b53b3b151f05d5ed7fa8
```

### 5.2 Encoding contract

- CPU only; FP32 model outputs; eager inference; no API and no GPU.
- MiniLM: 384 dimensions, mean pooling, no prefix, maximum 256 tokens including special tokens.
- Nomic: exact prefix `search_document: `, full 768 dimensions, mean pooling, no Matryoshka truncation.
- Explicit L2 normalization after pooling.
- Metric: cosine distance `1 - dot(x, y)` on normalized vectors.
- No network is permitted during measurement; all model/code loads use pinned local files.
- Pin execution to logical CPUs `0-15` but do not force a NUMA memory bind; set `OMP_NUM_THREADS=16`, `OPENBLAS_NUM_THREADS=16`, `MKL_NUM_THREADS=16`, PyTorch intra-op threads to 16 and inter-op threads to 1, inference mode on, dropout off, and deterministic algorithms on.
- A fixed canary set is encoded twice. Token IDs plus raw and normalized embedding byte hashes must match within the same process and a fresh process before corpus encoding.

The Nomic weights are not yet downloaded and its CPU canary remains OPEN. Metadata/LFS hashes were obtained without downloading weight variants.

### 5.3 Environment

Reuse the data-disk environment at `/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse/venv`:

```text
Python 3.12.3
sentence-transformers 3.4.1
transformers 4.57.6
tokenizers 0.22.2
torch 2.6.0+cpu
numpy 1.26.4
scipy 1.11.4
scikit-learn 1.5.2
pip-freeze sorted SHA-256: fd85cc59f76cff35cd96ac43066feb874f7564080fbe3bef90f188c1a6013602
```

Final environment lock and Nomic remote-code load compatibility remain OPEN until the canary completes.

## 6. Exhaustive neighborhood oracle

“Exact” means exhaustive over the frozen sampled background, not ANN search.

```text
ordered oracle universe = 8448 per source
pair-specific background = 8192 per source
query block = 256
corpus block = 4096
R = {16, 32, 64}
```

1. Store normalized embeddings as FP32. Compute block scores by exhaustive matrix multiplication.
2. For every merge into top-321, order the full candidate union by `(score descending, canonical_chunk_id ascending)` before truncation. `argpartition` before tie resolution is forbidden.
3. Self IDs are excluded for universe vertices. Real/Control-C anchors and targets query the full universe exhaustively; Control-A/B anchors use their self-excluded universe row.
4. Unit tests compare blockwise output with a full stable sort and include duplicate vectors, a tie exactly at rank 64, self-exclusion, and block-boundary ties.
5. For each pair/control, filter the top-321 rows/queries to its exact 8,192-member background, then take top-R. Persist top-321 IDs/scores plus filtered top-R records, not the full distance matrix.

For rank, append the excluded anchor to its exact 8,192-member fixed reference corpus, giving a pair-specific fixed reference population of exactly 8,193 items in every condition. `x_new` is absent. Rank ties use `(distance ascending, canonical_chunk_id ascending)`.

For each `R`, candidate order is independently:

```text
anchor
→ NN_R(anchor)
→ for each first-hop neighbor in NN order, its NN_R
→ stable first-occurrence deduplication
```

Maximum candidate-list sizes are 273, 1,057, and 4,161 for `R=16,32,64`. The anchor consumes candidate budget one but cannot be a target-neighborhood hit because it is excluded from the pair-specific background. Store `candidate_length` and the hit positions of the target top-R neighbors; this losslessly reconstructs the full recall-versus-candidate-count curve.

For each R:

```text
J_R = |NN_R(anchor) intersect NN_R(target)| / |NN_R(anchor) union NN_R(target)|
Coverage1_R = |NN_R(target) intersect NN_R(anchor)| / R
H2_R = NN_R(anchor) union union(NN_R(v) for v in NN_R(anchor))
```

The raw full-H2 recall and `|H2_R|` are descriptive. The primary two-hop endpoint is recall at the pairwise matched budget `C2=min(candidate_length_real,candidate_length_control)`, evaluated on both ordered candidate curves at the same `C2`.

The oracle runner and tests are OPEN and must be hashed before execution.

## 7. Deterministic paired controls

### Control A — random cross-document

- Candidate is a core-background vector from a different document, same source and checkpoint.
- Candidate payload hash must occur exactly once in the 8,448-item universe; otherwise it is not in the control pool. This makes anchor removal unambiguous.
- Match the **real `x_old` payload's** MiniLM-token length stratum: `1–64`, `65–128`, `129–192`, or `193–254` tokens.
- Choose the lowest `SHA256(canonical_json([seed, pair_id, candidate_id]))`; no retries based on metrics.
- Target remains `x_new`.
- Metrics use the candidate's exact leave-one-anchor-out 8,192-item background defined in Section 4.2.

### Control B — distance-matched cross-document

- Candidate is a core-background vector from a different document.
- Candidate payload hash must occur exactly once in the 8,448-item universe.
- Minimize `abs(distance(z,x_new) - distance(x_old,x_new))` exhaustively within the frozen background.
- Tie-break by canonical chunk ID in ascending UTF-8 byte order.
- Generate this control independently for each embedding model because the matching distance is model-specific.
- No caliper and no post-hoc fallback; target remains `x_new`; metrics use the exact leave-one-anchor-out background.

### Control C — non-adjacent same-section revision

For each `(document_path, section_path, occurrence)`, build its ordered payload-hash history only inside the frozen content-history interval `[lo,hi]`: the `lo` snapshot may be the earliest version, and child revision events are drawn from `lo..hi`; history never crosses `lo`. Collapse only consecutive equal hashes, so a rollback `A→B→A` remains three versions. If the adjacent real anchor is version `v[j-1]` and target is `v[j]`, choose the nearest earlier version `v[i]`, `i <= j-2`, whose hash differs from both `v[j-1]` and `v[j]`; deterministic choice is the maximum such `i`. Missing C is recorded as `MISSING_NO_NONADJACENT_VERSION`; there is no substitution.

Each control comparison uses only its own complete paired set, frozen before outcome inspection. Per-source minimum is 64 documents and 128 pairs for A, B, and C separately.

## 8. Metrics and document-clustered inference

Per pair and control, record displacement, old-anchor rank, `J_R`, `Coverage1_R`, raw full-H2 `Coverage2_R`, matched-budget `Coverage2Matched_R`, `|H2_R|`, and the complete candidate-efficiency curve. Rank is mathematically independent of R, so it is reported alongside all R values but tested once per control rather than triple-counted.

### 8.1 Paired effects

- Positive rank advantage: `log(rank_control + 0.5) - log(rank_real + 0.5)`.
- Positive overlap/coverage advantage: `metric_real - metric_control`.
- Positive curve advantage: `recall_real(R,C) - recall_control(R,C)` for every `R={16,32,64}` and frozen budget `C={16,32,64,128,256,512,1024}`; exhausted lists plateau.
- Within each document, average all retained pair effects first. Documents therefore receive equal inferential weight regardless of pair count.

### 8.2 Bootstrap and multiplicity

- 20,000 paired cluster-bootstrap replicates, resampling document-level mean effects with replacement.
- Bootstrap seed is `SHA256(canonical_json([master_seed, source, model, control, metric, R, C])) mod 2^64`; absent fields are JSON `null`.
- Random generator is NumPy `Generator(PCG64DXSM(seed))`.
- Let `T_obs` be the mean document effect. For the one-sided `H0: mean<=0`, center document effects by subtracting `T_obs`, bootstrap the centered values, and compute `p=(1 + count(T_null >= T_obs))/(B+1)`. Separately bootstrap uncentered values for confidence bounds.
- Within each source×model stratum, the primary family contains three controls × one rank endpoint plus three controls × three neighborhood endpoints × three R values = 30 tests. Report Holm-adjusted p-values and Bonferroni simultaneous one-sided lower bounds using quantile `alpha/30`, with family-wise `alpha=0.05`.
- Candidate curves form a separate family of three controls × three R values × seven budgets = 63 tests per source×model. Report Holm-adjusted p-values and Bonferroni simultaneous one-sided lower bounds using quantile `alpha/63`.
- Empirical lower quantiles use the zero-based order statistic `ceil((alpha/m)*(B+1))-1` after ascending sort; no interpolation.
- Report medians, document-equal means, corrected lower bounds, raw/adjusted p-values, document counts, pair counts, and missing-control counts. No arbitrary effect-size percentage is used.

### 8.3 Positive-signal rule

For every source×model stratum:

- a control is beaten only if its Holm-adjusted rank p-value is below 0.05 with simultaneous rank lower bound above zero, and both criteria hold for `J_R`, `Coverage1_R`, and matched-budget two-hop recall at at least two common R values;
- candidate efficiency must be non-worse at every frozen budget and strictly better at at least two budgets under corrected lower bounds;
- the above must reproduce in all four source×model strata. Pooling cannot rescue a failed stratum.

## 9. Final-label decision tree

Apply in this precedence order:

1. Any source/pairing/background/model/oracle/control/provenance/statistical/resource closure failure → `FAIL-W0-WORKLOAD-CLOSURE`.
2. Real pairs fail Control A in rank/neighborhood inheritance or Control-A matched-budget candidate efficiency → `KILL-NO-PAIR-LOCALITY`.
3. Real pairs beat A but fail Control B in rank/neighborhood inheritance or Control-B matched-budget candidate efficiency → `HOLD-GEOMETRIC-REPLACEMENT-ONLY`.
4. Real pairs beat A and B but fail Control C in rank/neighborhood inheritance or Control-C matched-budget candidate efficiency → `KILL-NO-TEMPORAL-LINEAGE-SIGNAL`.
5. Real pairs beat A, B, and C and pass candidate-efficiency replication → `HOLD-PAIR-LOCALITY-NOVELTY-REVIEW`.

No other label is permitted. A positive label authorizes only the separate prior-work novelty review named by GPT.

## 10. Time, memory, and storage guards

### 10.1 Hardware and placement

```text
CPU: 2 × Intel Xeon Gold 6348, 112 logical CPUs
GPU/API: disabled
data filesystem: /dev/nvme8n1, ext4
available at prelaunch: 760 GiB
system filesystem: forbidden for workload/model/temp/result materialization
```

All `HF_HOME`, `TRANSFORMERS_CACHE`, `TORCH_HOME`, `XDG_CACHE_HOME`, `PIP_CACHE_DIR`, and `TMPDIR` paths must point inside the W0 data root. Measurement starts with network disabled.

### 10.2 Hard gates

| Resource | Soft stop | Hard stop / outcome |
|---|---:|---|
| Incremental W0 NVMe allocation, including the reused 1.4 GiB environment in accounting | 9 GiB | 10 GiB → terminate and workload-closure failure |
| Peak RSS | 22 GiB | 24 GiB cgroup limit → terminate and workload-closure failure |
| Wall clock | projection above 3 h 30 m | 4 h watchdog, starting at post-authorization Stage 1 artifact closure and ending after the provenance seal → terminate and workload-closure failure |

Expected steady artifacts are below 3 GiB: 302 MiB Git metadata, about 0.64 GiB selected model weights, 1.4 GiB reused environment, under 0.2 GiB embeddings/graphs, plus source blobs/manifests/results. ONNX, PyTorch `.bin`, TensorFlow, OpenVINO, and unused model variants are forbidden downloads.

Before Stage 1, require host `MemAvailable >= 32 GiB` and cgroup-available memory at least 28 GiB; otherwise wait and do not start. Low raw NUMA `free` pages alone are not treated as headroom because reclaimable page cache is accounted through `MemAvailable`.

### 10.3 Staged run order after authorization

1. **Artifact closure:** selectively materialize eligible source blobs and required model/code files; verify every declared hash and total allocation.
2. **Workload closure:** build revision/pair/Control-C/background manifests; enforce minimum document/pair counts before embeddings.
3. **Canary:** deterministic chunker fixtures, both CPU model canaries, and exhaustive-top-k oracle tests.
4. **Projection gate:** time 1,024 background embeddings per model/source and one 2,048-node exact graph; if conservative projection exceeds 3 h 30 m, stop without changing N or models.
5. **Measurement:** embed frozen manifests, build four exhaustive graphs, generate controls/metrics, then run clustered inference.
6. **Provenance seal:** hash canonical config, runner/tests, source manifests, embeddings, graph records, metric rows, statistical tables, logs, and final result document.

No stage may silently shrink the sample, replace exact neighbors with ANN, change a model, or relax a control.

## 11. Provenance contract and closure table

Canonical JSON is `json.dumps(value, sort_keys=true, ensure_ascii=false, allow_nan=false, separators=(",",":"))` encoded as UTF-8 followed by **exactly one** LF. Arrays preserve input order; nested objects at every depth use sorted keys. Ordered compound keys and identities are JSON arrays, never language tuples or delimiter-joined strings. JSONL applies the same rule once per row and uses the declared row sort key. Every generated file gets SHA-256 plus byte count in `MANIFEST.sha256`; the result report binds the manifest hash and the Git commit containing the runner/config.

| Required item | State | Evidence / remaining action |
|---|---|---|
| Source URLs, immutable ranges, first-parent policy | CLOSED | Full SHAs, trees, commit counts and ordered-range hashes above |
| Rename/add/delete and path policy | CLOSED | Frozen above |
| Checkpoint path-candidate manifests | CLOSED | Counts and hashes above |
| Decoded source/pair/background/control manifests | OPEN | Requires selective blob materialization |
| Pair identity and multiset occurrence semantics | CLOSED-DESIGN | Requires fixtures and code hash |
| Model revisions, tokenizer and weight hashes | CLOSED-METADATA | LFS/tokenizer/config hashes above |
| Nomic local weights/remote-code CPU canary | OPEN | Selective fetch plus deterministic load test |
| Exact top-16/32/64 algorithm | CLOSED-DESIGN | Requires runner hash and full-sort tests |
| Three control generators | CLOSED-DESIGN | Requires implementation/test hashes and actual yields |
| Document-clustered statistics | CLOSED-DESIGN | Requires implementation/test hash |
| 4 h / 10 GiB / 24 GiB guards | CLOSED-DESIGN | Requires measured canary/projection evidence |
| Config/source/result hashes | PARTIAL | Remote/source metadata closed; executable config, runner, generated manifests and result hashes remain OPEN |

## 12. Review request

Please review the frozen design and choose one of two actions:

1. authorize artifact/runner preparation only, after which Codex will return the exact manifest, code, canary, projected-time, RSS, and storage hashes for the final run gate; or
2. return the prelaunch for revision.

Until the final run gate is explicitly issued after those OPEN items close, W0 remains at 0% measurement progress.

## 13. Amendment implementation and final preparation closure

This section supersedes the ordinal pairing design and all earlier OPEN-state tables.

### 13.1 Corrected implemented rule

- Every unchanged `(document path, normalized section path)` is aligned by a lexicographically stable, occurrence-aware LCS over exact full-payload SHA-256 values.
- Exact matches are anchors and excluded. Only an unmatched `1 -> 1` span is admitted; insertion, deletion, split, merge, many-to-many, and reorder spans receive explicit reason codes.
- Pair identity binds source, first-parent/child SHA, path, section, left/right exact anchors or boundaries, span ordinal, and both payload hashes.
- First-parent merge commits are explicitly diffed against parent one using NUL-safe `diff-tree -M100% --raw`; the previous `git log --name-status` enumeration was rejected because it omitted merge deltas.
- Control C includes `lo` plus every relevant content event, even when that commit is excluded from the real-pair population. Delete/rename-old tombstones and re-add/rename-new/copy-new segment starts prevent lineage from crossing a path-absence boundary. Control C reuses the same exact-LCS `1 -> 1` admission.

The final preparation suite passed 42/42 tests, including all ten mandatory fixtures, merge first-parent handling, multi-document history, delete/re-add segmentation, exact top-321 equivalence, controls, and clustered statistics.

### 13.2 Model and resource preparation

Both pinned CPU model canaries passed across two fresh processes. Token IDs, raw FP32 embeddings, normalized embeddings, shapes, and weights matched byte-for-byte. Nomic additionally closed its original/runtime config and pinned remote-code hashes.

Final canary comparison hashes:

- MiniLM: `69f060a5dab28f4aca44440a251a2276b13d12d7b000189788806f9564f6fa81`
- Nomic: `6a5746d34b454904f665c022263a298638a5b64953d6535c21b074d6c64da48e`

The shared stage clock and full storage ledger were enforced across processes. At the failure seal, wall time was 4,948.0 seconds, accounted storage was 2,404,774,044 bytes including the reused environment/model, W0-owned data was about 870 MiB, source-materialization peak RSS was 1,131,425,792 bytes, and host `MemAvailable` was about 256.1 GB. All W0-owned artifacts remained on `/dev/nvme8n1`.

### 13.3 Decisive workload-closure failure

The first source in canonical order, CPython, produced:

| Gate | Observed | Required | State |
|---|---:|---:|---|
| Fixed reference corpus | 8,448 | exactly 8,448 | pass |
| Control A | 538 pairs / 213 documents | at least 128 / 64 | pass |
| Control C | 25 pairs / 23 documents | at least 128 / 64 | **fail** |

Of 513 missing Control C records, 511 lack a distinct historical anchor, one lacks any non-adjacent version, and one cannot form an exact-LCS `1 -> 1` alignment. No fallback or substitution is permitted. The sealed workload summary SHA-256 is `214b9739134c087ccb8df18f55cf71552b97d2652ea48d85d7abe1926443dd71`.

By the frozen precedence rule, this is immediately:

```text
FAIL-W0-WORKLOAD-CLOSURE
```

Kubernetes materialization, full model-specific Control B encoding, projection, and every complete-workload outcome metric were skipped by fail-fast. Measurement remains 0%; `full_measurement=false`; the measurement CLI remains disabled. `PASS-W0-PRELAUNCH` is not issued.

Detailed preparation evidence: `codex/share/2026-07-20/rag_revision_pair_locality_w0_preparation_result_0720.md`.
