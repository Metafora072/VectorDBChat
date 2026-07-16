# Dynamic Vamana W1-C：R07 DiskANN Loader-Safe Continuation 门禁

**日期**：2026-07-16

**上游证据**：

* `codex/share/2026-07-16/dynamic_vamana_w1_r05_dgai_partial_results_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_r06_diskann_loader_stop_analysis_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_composed_one_percent_canary_r06_results_0716.md`

**裁决**：

* 接受 R05 DGAI `cp01-05` 为独立有效 system-level canary；
* 接受 R06 OdinANN `cp01-06` 为独立有效 system-level canary；
* R06 DiskANN 不包含有效查询样本；
* 授权新的 R07 只执行 DiskANN stale-static control；
* 不重跑 DGAI、OdinANN、CP01 或 checkpoint-1 GT。

---

# 1. 已冻结的动态系统结果

## 1.1 DGAI

有效来源：

```text
run     = pilot3_sift10m_w1_r05
attempt = DGAI/cp01-05
```

已完成：

* mutable private clone；
* pre-update query；
* 80,000 deletes 与 80,000 inserts；
* merge/publish；
* fresh-process visibility；
* active-set exact audit；
* 18/18 fresh probes；
* post-update query；
* immutable base content/mode audit。

正式摘要：

```text
ingestion              = 79.852742 s
ingestion throughput   = 1001.844 ops/s
restart visibility     = 103.025837 s
restart throughput     = 776.504 ops/s
```

R07 不重新执行 DGAI。

## 1.2 OdinANN

有效来源：

```text
run     = pilot3_sift10m_w1_r06
attempt = OdinANN/cp01-06
```

已完成：

* identity-v2 pre-update gate；
* mutable private clone；
* 80,000 deletes 与 80,000 inserts；
* live online visibility；
* save/publish；
* fresh-process visibility；
* active-set exact audit；
* 18/18 online probes；
* 18/18 fresh probes；
* checkpoint-1 post-update query；
* immutable base content/mode audit。

正式摘要：

```text
ingestion                 = 49.446224 s
ingestion throughput      = 1617.919 ops/s
online visibility         = 49.449186 s
online-visible throughput = 1617.822 ops/s
fresh visibility          = 147.467815 s
fresh-visible throughput  = 542.491 ops/s
```

R07 不重新执行 OdinANN。

---

# 2. 冻结 R06 OdinANN 证据

启动 DiskANN 前，生成：

```text
results/pilot3_sift10m_w1_r07/preflight/
├── r06_odinann_freeze.json
└── r06_odinann_evidence_manifest.tsv
```

并提交：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_r06_odinann_partial_results_0716.md
```

冻结审计必须验证：

* `FORMAL_W1_CANARY_OK` 存在；
* identity-v2 gate 为 pass；
  -marker 顺序完整；
  -`ingest_begin/end` 完整；
  -`online_visibility_probe_begin/verified` 完整；
  -`publish_begin/end` 完整；
  -fresh-process probe 完整；
  -active tags 与 checkpoint-1 exact match；
  -online probes 18/18；
  -fresh probes 18/18；
  -全部 pre/post query exit 0；
  -全部 result IDs active；
  -无 fatal、I/O error、OOM 或 OOM-kill；
  -OdinANN 使用 canonical io_uring binaries；
  -clone manifest v3 完整；
  -base content/mode 最终不变；
  -CP01 与 R02 GT preservation 为 pass。

partial report 必须包含：

* ingestion、online-visible、fresh-visible 时间和吞吐；
  -各阶段 NVMe read/write；
  -end-to-end device I/O；
  -payload-normalized writes；
  -persistent index growth；
  -clone 与 normalization 开销；
  -peak process-tree RSS 与 cgroup memory peak；
  -L29/L46 的 pre/post 三次 Recall、QPS、P99 和 mean I/O；
  -所有正式证据文件的 size/SHA256。

冻结审计失败时不得启动 DiskANN。

---

# 3. R06 DiskANN 失败边界

R06 DiskANN：

```text
phase     = diskann_stale_static_control
exit_code = 127
```

失败发生在动态加载器阶段：

```text
libtcmalloc.so.9.9.5: cannot open shared object file
```

该 attempt：

-未进入程序 `main()`；
-未读取 NVMe；
-未产生 Recall；
-未生成有效 result IDs；
-未修改 checkpoint-0 base。

因此 R06 DiskANN 目录只作为 loader-failure 证据保留，不能参与最终结果。

---

# 4. 冻结 DiskANN runtime 环境

新增：

```text
w1_diskann_runtime_manifest.py
```

生成：

```text
diskann_runtime_manifest.json
```

至少记录：

```text
binary realpath
binary SHA256
ELF interpreter realpath
DT_NEEDED entries
每个依赖的 resolved realpath
每个实验私有依赖的 size/SHA256
runtime library directories
loader command
```

DiskANN binary 必须为：

```text
SHA256 =
631fc53b4514fdac8325a7d789792ff6d19fb007e5442410898ec4a9505d4c3e
```

gperftools library 必须为：

```text
realpath =
.../build/gperftools-install/lib/libtcmalloc.so.9.9.5

SHA256 =
9035515aa26ebfaa2cf390291378e0ccba66175ba8291b92aa32e92f97a8b904
```

所有 `DT_NEEDED` 必须解析成功，不允许出现：

```text
not found
```

不得依赖：

-用户交互式 shell；
-当前终端继承的 `LD_LIBRARY_PATH`；
-系统级安装；
-修改 `/etc/ld.so.conf`；
-未记录的 fallback library。

---

# 5. Runtime environment 构造

`w1_diskann_stale_control.sh` 必须显式构造 runtime environment。

至少包含：

```text
gperftools-install/lib
```

若 frozen loader manifest 表明还需要实验私有的 OpenBLAS、jemalloc 或其他目录，则一并显式加入。

不得直接继承任意调用者的完整 `LD_LIBRARY_PATH`。

推荐：

```bash
runtime_libs="冻结并排序后的目录列表"
export LD_LIBRARY_PATH="$runtime_libs"
```

同时把最终值写入：

```text
runtime_environment.json
```

包括：

-完整 `LD_LIBRARY_PATH`；
-每个目录的 canonical realpath；
-loader manifest SHA256；
-binary SHA256；
-systemd scope；
-uid/gid；
-CPU/NUMA 设置。

---

# 6. Loader 回归测试

新增：

```text
w1_diskann_loader_tests.py
```

输出：

```text
results/pilot3_sift10m_w1_r07/preflight/
diskann_loader_tests.json
```

## 6.1 正向测试

在与正式查询相同的条件下：

-相同运行用户；
-相同 systemd scope 属性；
-CPU 0–23；
-NUMA node 0；
-清理后的环境；
-相同 binary；
-相同 runtime library path。

使用 ELF loader 的 list/verify 模式或等价只读方法，不进入查询主逻辑。

要求：

-全部依赖成功解析；
-`libtcmalloc.so.9.9.5` 指向冻结 realpath；
-size/SHA256 匹配；
-退出码为 0。

## 6.2 负向测试

移除冻结的 gperftools 路径。

要求稳定复现：

-退出码 127 或明确 loader failure；
-同一 `libtcmalloc.so.9.9.5` 缺失错误；
-不进入查询主逻辑；
-不创建正式 result；
-不读取 NVMe；
-不修改 DiskANN base。

## 6.3 Query smoke

在临时 scratch 目录中执行一次最小真实加载 smoke：

-使用冻结 binary；
-使用 checkpoint-0 index；
-使用正确 runtime path；
-只允许最小 query 输入；
-验证程序确实越过 loader 并读取 index；
-不写入正式 R07 result tree。

smoke 结束后验证 immutable base manifest 不变。

---

# 7. R07 目录

使用：

```text
results/pilot3_sift10m_w1_r07/
```

DiskANN attempt：

```text
DiskANN/stale-cp00-07
```

R07 不创建：

```text
formal/pilot3_sift10m_w1_r07/DGAI
formal/pilot3_sift10m_w1_r07/OdinANN
```

最终报告：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_composed_one_percent_canary_r07_results_0716.md
```

---

# 8. R07 continuation preflight

在同一个 global flock 内验证：

* R05 DGAI freeze 为 pass；
* R06 OdinANN freeze 为 pass；
  -R06 状态为 `stopped_failed`；
  -R06 停止阶段为 DiskANN stale control；
  -R06 DiskANN 没有有效 query point；
  -R06 OdinANN 已完整成功；
  -R02 GT SHA256 为冻结值；
  -CP01 preservation 为 pass；
  -DiskANN binary hash；
  -DiskANN checkpoint-0 base content manifest；
  -query SHA256；
  -checkpoint-1 GT SHA256；
  -runtime loader manifest；
  -无 `not found` dependency；
  -项目 NVMe major:minor；
  -无 active `dv-w1-*` scope；
  -process identity scan 通过；
  -free space 门禁通过；
  -R07 result target 不存在。

---

# 9. DiskANN stale-static control

固定执行：

```text
L  = 29, 53
Tq = 1
每点三次
```

使用：

```text
checkpoint-0 immutable DiskANN index
checkpoint-1 exact GT
```

独立 systemd scope：

```text
AllowedCPUs = 0-23
NUMA membind = node 0
CPU/Memory/IO accounting enabled
```

每个点必须满足：

* loader audit 已通过；
  -exit code 0；
  -Recall、QPS、latency 和 mean I/O finite；
  -result shape 正确；
  -无 fatal/assertion/I/O error；
  -无 OOM/OOM-kill；
  -NVMe read bytes 大于 0；
  -binary/query/GT/base identity 精确匹配。

作为 stale negative control：

-允许返回 checkpoint-1 已删除 tag；
-不要求 result IDs 全部属于 checkpoint-1 active set；
-不得参与 update throughput 排名；
-不得解释为动态系统。

---

# 10. Final composed result

R07 通过后，最终组合证据为：

```text
DGAI    → R05 / DGAI / cp01-05
OdinANN → R06 / OdinANN / cp01-06
DiskANN → R07 / DiskANN / stale-cp00-07
GT      → R02 / gt_cp01
CP01    → frozen shared checkpoint-1 artifacts
```

最终报告必须明确：

> 三个系统结果来自多个严格隔离、fail-closed continuation attempt，不是一次无中断 controller run。

报告至少包含：

## DGAI

* ingestion 与 restart-visible throughput；
  -阶段 I/O；
  -空间增长；
  -memory；
  -pre/post query stability；
  -correctness 与 visibility。

## OdinANN

* ingestion、online-visible、fresh-visible throughput；
  -阶段 I/O；
  -空间增长；
  -memory；
  -pre/post query stability；
  -online/fresh correctness。

## DiskANN

-六个 stale-control raw points；
-Recall、QPS、P99、mean I/O；
-NVMe reads；
-loader/runtime identity。

## 对比边界

允许讨论：

-固定 W0 policy 下的 1% churn stability；
-update ingestion cost；
-不同 visibility semantics；
-device writes；
-persistent growth；
-stale static baseline 的 Recall 退化。

不得：

-将 DGAI restart-visible 与 OdinANN online-visible当成相同语义直接排名；
-称 checkpoint-1 结果为 matched-Recall frontier；
-将 DiskANN stale control视为动态更新系统；
-声称三个系统来自同一无中断 attempt。

---

# 11. 失败规则

R07 任一阶段失败：

-立即停止；
-保留全部证据；
-不自动重试；
-不复用 R07；
-不重跑动态系统；
-不修改 L；
-不调整 GT；
-不进入更高 churn。

---

# 12. 完成后停止

R07 完成后停止，不自动执行：

* 5%/10%/20% replacement；
  -DiskANN rebuild；
  -checkpoint-1 Recall refinement；
  -mixed query/update workload；
  -W2；
  -DEEP/GIST。

---

# 13. 最终裁决

R06 OdinANN 是完整有效的 system-level canary，应与 R05 DGAI 对等冻结。

R06 DiskANN 仅暴露独立 worker 缺少冻结 runtime library path，不包含任何有效性能样本。

授权 R07 只修复和验证 DiskANN loader 环境，并完成 stale-static control与最终 composed W1 1% report。
