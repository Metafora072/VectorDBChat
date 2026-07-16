# Dynamic Vamana W1 R06 OdinANN Partial Results

R06 OdinANN `cp01-06` 是独立有效的 W1 1% system-level canary。R06 后续 DiskANN loader stop 不使该 attempt 失效；R07 不重跑 OdinANN。

## Update、可见性与资源

- ingestion：`49.446224 s / 1617.919 ops/s`。
- online visibility：`49.449186 s / 1617.822 ops/s`。
- fresh-process visibility：`147.467815 s / 542.491 ops/s`。
- ingest NVMe R/W：`45313896448/12129304576 B`；publish R/W：`24870457344/8192376832 B`；end-to-end R/W：`78375845888/28545339392 B`。
- 40,960,000 B inserted payload 对应 ingest/publish/end-to-end write ratio：`296.126x / 200.009x / 696.908x`。
- persistent growth：`8480140468 B`，即 payload 的 `207.035x`。
- update probe wall / peak RSS / cgroup peak：`150.808 s / 2148999168 B / 10857242624 B`。
- mutable clone wall：`12.193 s`，apparent/allocated：`8480140468/8480157696 B`，clone NVMe R/W：`0/109199360 B`。
- permission normalization：`0.000172 s`，`7` 次 metadata operation。

## Pre/Post query raw values

| Phase | L | Recall@10 r1/r2/r3 | QPS r1/r2/r3 | P99(us) r1/r2/r3 | Mean I/O r1/r2/r3 |
|---|---:|---|---|---|---|
| pre_cp00 | 29 | 0.95085 / 0.95072 / 0.95056 | 1595.14 / 1645.41 / 1559.89 | 855.0 / 833.0 / 895.0 | 51.24 / 51.17 / 50.97 |
| pre_cp00 | 46 | 0.98000 / 0.97963 / 0.97981 | 1374.23 / 1235.29 / 1244.34 | 865.0 / 981.0 / 1102.0 | 65.86 / 64.71 / 65.63 |
| post_cp01 | 29 | 0.94991 / 0.95022 / 0.94964 | 1500.03 / 1617.36 / 1749.58 | 891.0 / 804.0 / 741.0 | 51.10 / 51.42 / 50.69 |
| post_cp01 | 46 | 0.97933 / 0.97927 / 0.97934 | 1296.46 / 1328.84 / 1353.18 | 1020.0 / 930.0 / 936.0 | 65.95 / 65.95 / 65.91 |

Identity-v2、active set exact、18/18 online probes、18/18 fresh probes、12 次 query resource/ID audit、clone-v3、immutable-base content/mode 与停止后的 CP01/R02 GT preservation 均通过。全部正式 result evidence 的 size/SHA256 位于 R07 `preflight/r06_odinann_evidence_manifest.tsv`。
