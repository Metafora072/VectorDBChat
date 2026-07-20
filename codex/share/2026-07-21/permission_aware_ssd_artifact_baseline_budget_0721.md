# P0 X2/X3/X4/X5 — Artifact、Simulator、强基线与预算

**Scope:** 只读检查与计划；未下载、编译、运行实验或修改 ANN 源码。

## 1. Artifact status

| Item | Local status | Decision |
|---|---|---|
| GateANN | 无源码、build、`search_disk_index_fa` | 复现前需单独批准网络获取与依赖闭合 |
| PipeANN-Filter | 多个本地副本均在 commit `9e7a193...`，但全部 dirty | 不能称 clean official artifact |
| Filtered binaries | 某 OdinANN build 有 filtered binaries，但源码 dirty，且默认缺 `libtcmalloc.so.9.9.5` | 只作路径证据，不作 baseline 数字 |
| SIFT1M | `full_1m.bin` 512,000,008 B；query 5,120,008 B；普通 GT 已在数据盘 | 可复用，不下载数据 |
| ACL inputs | 无 node labels、`.spmat`、query binding、authorized filtered GT | 必须由独立 generator 产生 |
| RocksDB runtime | 本机当前审计未确认可直接使用 | X4 只能作能力审计；U 轴实测先 HOLD |

1M 不是 GateANN 或 PipeANN-Filter 的论文正式规模。GateANN artifact 的公开数据从 YFCC10M/BigANN100M 起，quick validation 固定 BigANN100M；PipeANN-Filter 公开示例也从 YFCC10M 起。因此 1M 结果只能标为 mechanism/artifact-path preflight，不能宣称复现 paper speedup。

## 2. Official reproduction skeletons

### GateANN

```text
git clone https://github.com/GyuyeongKim/GateANN-public.git $DATA_SRC/GateANN-public
cmake -S . -B $DATA_BUILD/GateANN -DCMAKE_BUILD_TYPE=Release
cmake --build $DATA_BUILD/GateANN -j16

build/tests/build_disk_index uint8 BASE PREFIX 128 200 32 80 16
build/tests/search_disk_index_fa ... mode=2 ...
build/tests/search_disk_index_fa ... mode=8 ... Rmax=32
```

注意：official README 正文一处 clone 命令写 `GateANN.git`，实际公开仓库名为 `GateANN-public`；执行前必须冻结真实 URL 与 commit。1M adapter 需生成 node/query labels 与 authorized filtered GT，不能直接运行 `quick_validate.sh`。

### PipeANN-Filter

```text
cmake -S . -B $DATA_BUILD/PipeANN -DIO_ENGINE=uring -DUSE_TCMALLOC=ON
cmake --build $DATA_BUILD/PipeANN -j16

build/tests/build_disk_index_filtered float SIFT1M PREFIX \
  96 0 128 32 24 16 l2 pq label_spmat BASE_ACL_SPMAT
build/tests/search_disk_index_filtered float PREFIX 1 32 QUERY FILTERED_GT \
  10 l2 pq CONFIG 0 10 20 40 80
```

`R_dense=0` 只验证 build/predicate/statistics path；若验证 two-hop IN_FILTER，再单独审议 `R_dense=512`。公开 YFCC 风格 `R_dense=1500` 会使 1M index 约 7.6 GiB，连同源码、临时与数据可能突破 10 GiB，禁止默认执行。

## 3. Page-cache finding

- GateANN/PipeANN graph index 使用 `O_DIRECT + io_uring`，不会被 Linux page cache 吸收；GateANN FullAdj `mmap` 常驻和 filter store 常驻属于算法设计，必须计入 DRAM。
- PipeANN-Filter attribute index 当前以普通 buffered fd 打开。1M policy posting/sorted index 仅 MB 到几十 MB，会迅速进入本机 238 GiB available DRAM 的页缓存。
- 因此：graph I/O 可直接作 SSD 证据；1M policy I/O 必须分别标 cold/warm。全局 `drop_caches` 会干扰同机任务，需二次批准和独占窗口；正式轴 B 更理想的方案是审计独立只读 `O_DIRECT` fd，不能未经审查直接改全部 attribute update path。

## 4. X3 independent simulator interface

```text
validate     manifest/hash/scale/page-map/GT checks
simulate-q   deterministic ACL distribution + traversal
replay-io    replay frozen aligned page events on data disk
simulate-m   policy representation/cache analysis
simulate-u   update stream + MVCC/page-prefix overlay
summarize    paired statistics/resource/decision report
```

Core interfaces:

```text
GraphView.neighbors(node_id)       GraphView.page(node_id)
DistanceOracle.distance(qid, node)
PolicyView.may_match(node, query, snapshot)
PolicyView.exact_allow(node, query, snapshot)
PageSource.read(file_role, page_id)
UpdateStore.apply(op)              UpdateStore.snapshot()
Planner.search(query, snapshot, trace_sink)
```

Simulator 的逻辑 I/O 不能冒充设备延迟；data-disk replay 只能测既定事件的物理 I/O，不能反向改变搜索轨迹。完整 event trace 只保留 32 个诊断 query，其余只聚合。

## 5. X4 strongest natural baseline

### RocksDB/MVCC native or configured

- WAL、sync durability、recovery、WriteBatch；
- sequence number、snapshot read；
- ordered key、prefix extractor/Bloom、partitioned index/filter；
- block cache、memtable、SST、compaction、range tombstone/filter；
- Iterator/Seek/prefix scan/MultiGet；
- checkpoint、PerfContext、I/O statistics、rate limiter；
- direct read 与 direct flush/compaction；
- `(graph_generation, graph_page, policy_atom, begin_csn, node_id)` sortable key；
- fixed cache/memtable/background budget 与独立 column family。

### Small application glue

- node→page/generation mapping、touched-page dedup/MultiGet；
- query snapshot token 映射、query-side role closure、exact verifier；
- continuation/refill、MVCC encoding/GC、page summary rebuild/migration。

### Not native

- policy 与 graph 共享同一次物理 4 KiB read；
- ANN frontier/tunneling/reachability；
- authorized-recall invariant；
- graph/policy cache 的天然统一；
- graph repack 后稳定 page identity；
- 自动判定影响 approximate traversal 的 policy atom；
- zero-extra-I/O guarantee。

未来候选与 baseline 必须共享 graph/query/ACL/snapshot/seed、page mapping、exact verifier/refill、总 policy memory、CPU/QD、I/O mode、WAL/sync/batch、compaction debt 与 build/recovery/space 成本。不得只使用 node-keyed 弱对照。

## 6. Proposed future budget

### Recommended first approval package: PipeANN G0 + Axis A

| Run | Time cap | RSS cap | New data-disk cap |
|---|---:|---:|---:|
| identity/hash/path preflight | 20 min | 4 GiB | 0.2 GiB |
| A1/A5 semantic smoke | 10 min | 4 GiB | 0.2 GiB |
| matched-selectivity A1-A5 characterization | 65 min | 6 GiB | 0.8 GiB |
| representative direct graph-I/O replay | 45 min | 4 GiB | 1.0 GiB |
| summary | 10 min | 2 GiB | 0.1 GiB |
| clean build/adapter reserve | 50 min | 16 GiB | 3.0 GiB |
| **Total + guard** | **200 min + 40 min guard** | **<20 GiB** | **hard cap 8.5 GiB** |

GateANN、`R_dense=512/1500`、RocksDB U 轴实测与全局 `drop_caches` 均不包含在首包中，必须单独审议。系统盘不得存放 source/build/DB/WAL/SST/trace/core/log/TMP/cache；若依赖闭合需要 apt/pip 全局写入，标记 `HOLD-DEPENDENCY`。

## 7. Stop conditions

- 缺 input hash、graph generation、node→page mapping 或 authorized GT；
- dirty binary 被误当 official result；
- 大工件路径不在 `/dev/nvme8n1`；
- RSS 20 GiB soft / 24 GiB hard、data 8.5 GiB soft / 10 GiB hard、wall 3h45 soft / 4h hard；
- unauthorized final result、snapshot contract 不一致或固定 seed 不可复现；
- requested/submitted/completed/device bytes 无法闭合；
- 系统盘出现 >64 MiB 非预期写入。

## Primary sources

- GateANN artifact: <https://github.com/GyuyeongKim/GateANN-public>
- GateANN paper: <https://arxiv.org/html/2603.21466>
- PipeANN artifact: <https://github.com/thustorage/PipeANN>
- PipeANN C++ guide: <https://github.com/thustorage/PipeANN/blob/main/docs/cpp-interface.md>
- PipeANN-Filter paper: <https://arxiv.org/html/2605.17992>
