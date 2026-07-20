# RAG Revision-Pair Locality W0：Artifact Preparation Result

**Time:** 2026-07-20 21:14:26（UTC+8）  
**Scope:** GPT-authorized artifact/runner preparation only  
**Measurement:** not authorized; not started  
**Final preparation label:** `FAIL-W0-WORKLOAD-CLOSURE`

## 1. Decisive result

The stricter occurrence-aware exact-LCS generator produced a valid CPython source workload, but the mandatory non-adjacent same-section Control C population did not meet the frozen minimum.

| CPython source gate | Observed | Required | Result |
|---|---:|---:|---|
| Selected real pairs | 538 pairs / 213 documents | supports each paired control | closed |
| Fixed reference corpus | 8,448 items | exactly 8,448 | pass |
| Control A | 538 pairs / 213 documents | at least 128 / 64 | pass |
| Control C | 25 pairs / 23 documents | at least 128 / 64 | **fail** |

Only 4.65% of selected pairs and 10.80% of selected document clusters retained a complete strict Control C. Of the 513 missing controls, 511 were `MISSING_DISTINCT_HISTORICAL_ANCHOR`, one was `MISSING_NO_NONADJACENT_VERSION`, and one was `MISSING_NO_EXACT_LCS_1_TO_1_ALIGNMENT`. The gate forbids substitution, fuzzy matching, post-metric rescue, or a smaller minimum.

This is a workload-closure failure, not a negative locality outcome. No rank, Jaccard, coverage, candidate-efficiency, ANN, update, I/O, or SSD metric was computed.

## 2. Correctness closure before the source run

The implementation was amended before accepting any source counts:

- exact payload-SHA LCS anchors; only unmatched `1 -> 1` spans become real pairs;
- explicit insertion, deletion, split, merge, many-to-many, and reorder reason codes;
- first-parent commits, including merges, are explicitly compared with `diff-tree -M100% --raw -z`;
- Control C history includes `lo` and all relevant path-content events, including commits excluded from the real-pair population;
- delete and rename-old create tombstones; re-add/rename-new/copy-new start a new path-existence segment, so Control C cannot cross a deletion or rename boundary;
- Control C target identity uses the occurrence-aware canonical chunk ID within the target snapshot, not a cross-version raw ordinal;
- no smaller reference universe, missing-reserve fallback, or minimum-count bypass exists.

The final suite passed 42/42 tests. It includes the ten mandatory alignment fixtures, merge first-parent coverage, multi-document history, delete/re-add segmentation, exact top-321 versus independent full stable sort, Control B generator tests, and clustered-statistics tests.

## 3. Sealed evidence

| Artifact | SHA-256 |
|---|---|
| Workload failure seal | `214b9739134c087ccb8df18f55cf71552b97d2652ea48d85d7abe1926443dd71` |
| CPython source summary | `ace7436489c98e14975cc81550033d59f5bb137f967efb0eee93ce08aef20d0c` |
| Selected-pair manifest | `13e7d99cdf1acadb01880a00929b6bf07538350ecad3668e3a279e7d7fcb3b34` |
| Fixed-reference manifest | `0b084ae63e6e46e35b932699ab36ad0b00b8e8f00639559c2e56a7a0008d0e16` |
| Control A manifest | `97a1d85c27543da9cfafb0761465a963180febd9f3112c66a1692f04196b83f9` |
| Control C manifest | `a62c352b43fe47a7513ada8edf61aa40a298268edcd41d7701bb1b8984d8abd3` |
| Control C missing manifest | `be6270159f77d9051f4e8501d29c8527581791d9b82dbe3ccac31dcecf19d311` |
| Final MiniLM fresh-process comparison | `69f060a5dab28f4aca44440a251a2276b13d12d7b000189788806f9564f6fa81` |
| Final Nomic fresh-process comparison | `6a5746d34b454904f665c022263a298638a5b64953d6535c21b074d6c64da48e` |
| Preparation config | `6f11e19d77ee62615b829f882c721fe61b5f2f6419546e01005e57e122613596` |
| Runner | `f9937c36f35480c7c484a57a1326de3b38d65c5a735f78d608761fcf3042a330` |
| Workload generator | `8ecc1dcf0ebda699d0c82ab67a9d818fde73754fa615cd60ed343d2981a92e47` |
| Shared venv `pip freeze` | `fd85cc59f76cff35cd96ac43066feb874f7564080fbe3bef90f188c1a6013602` |

The workload failure seal re-read every CPython JSONL, verified its byte hash and non-empty-line count, and recorded the source summary hash. The complete per-file hashes remain in the seal and source summary on the data disk.

## 4. Model and resource records

Although the source gate later failed, preparation had already closed both pinned CPU canaries. MiniLM and Nomic each matched token-ID, raw FP32 embedding, normalized embedding, shape, and weight hashes across two fresh processes. Nomic also verified the original config, locally rewritten runtime config, both pinned remote-code files, and every required tokenizer/model artifact.

At the failure seal:

- shared stage wall time: 4,948.0 seconds from the frozen preparation start;
- accounted storage: 2,404,774,044 bytes, including the 1.4 GiB reused venv and MiniLM snapshot;
- W0-owned data-disk directory: approximately 870 MiB;
- peak RSS during CPython source materialization: 1,131,425,792 bytes;
- host `MemAvailable`: approximately 256.1 GB;
- data disk free space: approximately 759 GB.

All W0-owned models, Git objects, caches, manifests, and temporary files remained on `/dev/nvme8n1`. The system disk was not used for experiment data.

## 5. Fail-fast actions

The following authorized preparation tasks were deliberately skipped after the decisive source failure:

- Kubernetes source materialization and counts;
- full model-specific Control B encoding/manifests;
- projection canary;
- any complete-workload outcome measurement.

`full_measurement` remains `false`, and the runner's `measurement` command remains a hard stop. `PASS-W0-PRELAUNCH` is not issued. The only valid next action is GPT review of this workload-closure failure; continuing the same W0 would require a new gate that explicitly changes the source/range or removes Control C, which would be a different experimental claim.
