# Dynamic Vamana W1 R05 DGAI Partial Results

R05 DGAI 是独立有效的 1% canary 证据；R05 后续 OdinANN pre-update stop 不使该 attempt 失效。R06 不重跑 DGAI。

## Update 与资源

- ingestion: `79.852742s`, `1001.844 ops/s`
- restart visibility: `103.025837s`, `776.504 ops/s`
- ingest NVMe R/W: `40366260224/2300735488` B
- publish NVMe R/W: `13885784064/5461368832` B
- end-to-end NVMe R/W: `54258987008/7762075648` B
- persistent growth: `0` B
- update probe elapsed / peak RSS / cgroup peak: `104.908s / 3785252864 B / 17766035456 B`
- mutable clone: `18.836s`, apparent/allocated `14131068900/14130733056` B, clone NVMe R/W `0/314396672` B
- permission normalization: `0.000263s`, `17` metadata operations

## Pre/Post query raw values

| Phase | L | Recall@10 (r1/r2/r3) | QPS median | P99 median(us) |
|---|---:|---|---:|---:|
| pre_cp00 | 64 | 0.9514 / 0.9515 / 0.9516 | 1288.84 | 993.0 |
| pre_cp00 | 128 | 0.9800 / 0.9802 / 0.9801 | 844.41 | 1390.0 |
| post_cp01 | 64 | 0.9509 / 0.9498 / 0.9511 | 1253.20 | 1008.0 |
| post_cp01 | 128 | 0.9802 / 0.9803 / 0.9803 | 859.28 | 1367.0 |

Active set exact，fresh probes `18/18`，online visibility 对 DGAI 明确为 unsupported；所有 12 次查询均 exit 0、结果 active、metric finite 且真实读取 NVMe。完整逐文件冻结清单位于 R06 `preflight/r05_dgai_evidence_manifest.tsv`。
