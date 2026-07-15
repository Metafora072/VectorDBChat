# Dynamic Vamana W1-C：Formal Execution Preflight 门禁

**日期**：2026-07-15
**上游报告**：`codex/share/2026-07-15/dynamic_vamana_w1_formal_path_integration_0715.md`
**裁决**：**FORMAL-PATH REPLAY PASS；SIFT10M EXECUTION HOLD**

---

# 1. 已通过部分

SIFT1M/16-replacement formal-path replay 验收通过。

已验证：

* micro/formal 共用状态机；
  -唯一 global flock；
* DGAI 与 OdinANN 严格串行；
  -独立 systemd scope；
* CPU 0–23；
* NUMA node 0；
* clone 后 pre-update query；
  -原生 insert/delete/merge/save；
* DGAI online visibility unsupported；
* OdinANN live visibility；
  -fresh-process visibility；
  -persisted active-tag exact-set audit；
  -result-ID probes；
  -post-update query；
  -final immutable-base manifest；
  -phase-scoped NVMe accounting；
  -失败路径 fail closed。

这些结果证明共享状态机可用。

---

# 2. 正式路径的阻塞项

## F7. Formal base 路径仍指向 SIFT1M

当前 orchestrator 无论 mode 是 micro 还是 formal，都设置：

```text
DGAI:
index/atlas1m/DGAI/sift1m

OdinANN:
index/atlas1m/OdinANN/sift1m
```

并使用：

```bash
[[ $mode == micro || $base == *"sift10m"* ]] || true
```

该语句不会阻止错误路径。

必须改成显式表：

```text
micro/DGAI
→ index/atlas1m/DGAI/sift1m

micro/OdinANN
→ index/atlas1m/OdinANN/sift1m

formal/DGAI
→ formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index

formal/OdinANN
→ formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index
```

formal 模式必须断言：

```text
base realpath contains the expected SIFT10M F0 attempt
base manifest hash equals frozen checkpoint-0 manifest
```

禁止 `|| true`。

---

## F8. CP01 文件名映射错误

正式 CP01 实际文件为：

```text
replace_cp01_80k.bin
active_cp01.tags.bin
visibility_probes.bin
visibility_probes.json
active_cp01.bin
```

当前 orchestrator 传入的是 micro 文件名：

```text
trace.bin
active.tags.bin
probes.bin
probes.json
```

请为 micro/formal 分别定义完整 artifact map，不允许通过目录名隐式猜测。

formal 模式必须传：

```text
--trace                 replace_cp01_80k.bin
--expected-active-tags  active_cp01.tags.bin
--probe-queries         visibility_probes.bin
--probe-spec            visibility_probes.json
```

启动前逐个验证：

* realpath；
  -大小；
  -SHA256；
  -manifest identity；
  -trace validation；
  -probe positions 恰好 9 个；
  -operation count 恰好 80,000。

---

## F9. Full corpus 路径未传递

shared runner 当前自己推导：

```text
formal:
${dataset-dir}/full_10m.bin
```

而 `dataset-dir` 是 `datasets/sift10m/w1_cp01`。

应新增显式参数：

```text
--full-corpus
```

formal 传：

```text
datasets/sift10m/full_10m.bin
```

micro 传：

```text
datasets/sift1m/full_1m.bin
```

删除 runner 内部依据 mode 拼接文件名的逻辑。

driver 使用的 corpus realpath 和 SHA256 必须写入 attempt manifest。

---

## F10. Clone 白名单不包含正式 run

当前 clone helper 只允许：

```text
formal/pilot3_w1_*
```

正式目标为：

```text
formal/pilot3_sift10m_w1
```

请改为显式允许：

```text
formal/pilot3_w1_formal_path_replay_*
formal/pilot3_sift10m_w1/*
```

不能改成宽泛的 `formal/*`。

同时正式 attempt 名使用：

```text
cp01-01
```

不要继续叫 `replay-01`。

---

## F11. OdinANN 必须保持 io_uring identity

当前 rebuild manifest 中：

```text
-DIO_ENGINE=aio
linked library: libaio
```

这不是 W0 的 OdinANN-uring artifact。

正式 W1 必须使用：

```text
-DIO_ENGINE=uring
```

并验证：

1. CMake 输出明确包含 `Using system liburing`；
2. compile definitions 包含 `USE_URING`；
3. `ldd` 包含 `liburing`；
4. binary 不回退为 AIO；
5. query binary 与 update driver 使用同一 I/O-engine build tree；
6. W0 compatibility patch、result-ID patch、W1 driver patch 的顺序固定；
7. canonical binary SHA256 写入 manifest。

如果 uring 配置失败，必须停止；不允许自动 fallback 到 AIO。

---

## F12. Canonical rebuild identity

F1 目前仍未完全通过，因为 clean checkout rebuild 不能重现 canonical binary hash。

请统一：

```text
-ffile-prefix-map
-fdebug-prefix-map
-fmacro-prefix-map
SOURCE_DATE_EPOCH
相同 compiler/linker
相同 CMake flags
相同依赖库 realpath
```

对以下目标至少完成两次独立 clean build：

```text
DGAI w1_canary
DGAI search_disk_index
OdinANN-uring w1_canary
OdinANN-uring search_disk_index
```

要求两次 clean build byte-identical。

formal orchestrator 启动前重新计算 binary SHA256，并与冻结 manifest 精确匹配。

---

# 3. Orchestrator 完整性

正式唯一入口必须包含：

```text
global lock
→ artifact rebuild/hash preflight
→ CP01 trace preparation
→ trace validation
→ CP01 active-vector materialization
→ exact GT computation
→ GT validation
→ DGAI cp01-01
→ DGAI complete validation
→ OdinANN cp01-01
→ OdinANN complete validation
→ DiskANN stale-static control
→ final report
→ stop
```

当前 formal 分支只是消费已经存在的 CP01/GT，尚未把 preparation 纳入唯一串行入口。

可以拆成 phase 脚本，但必须由一个顶层 orchestrator 串联，并共享同一 flock。

任一阶段失败：

* 停止；
  -不执行后续阶段；
  -保留 attempt；
  -不自动重试；
  -不更换参数；
  -不覆盖输出。

---

# 4. Formal preflight 模式

在执行真实 CP01 前，新增：

```bash
run_w1_cp01_formal.sh preflight
```

preflight 不生成大文件、不 clone、不执行 update。

它必须验证：

-所有路径解析到预期 NVMe；

* SIFT10M base 为正确 8M F0 index；
  -不存在 micro artifact 路径；
* CP01 输出目标尚不存在；
* frozen binary hashes；
* OdinANN 为 io_uring；
* 150 GB free-space；
* compute-groundtruth binary；
* query/active/tag/full-corpus identity；
  -通知配置；
  -全局 lock；
* systemd/NUMA/cgroup runtime canary。

输出：

```text
formal_preflight.json
```

且必须包含所有 resolved realpaths。

---

# 5. 再次 replay 的范围

由于 shared runner、artifact map、base selection 和 Odin I/O engine 都会修改，请再运行一次 1M/16-op formal-path replay。

这一次必须使用：

* canonical reproducible binaries；
* OdinANN io_uring；
  -修复后的显式 full-corpus 参数；
  -与正式模式相同的 artifact-map resolution 代码。

通过后提交审查，不自动运行 SIFT10M。

---

# 6. 当前授权

当前只授权：

```text
修复 F7–F12
→ 完成 deterministic uring rebuild
→ formal preflight
→ 1M/16-op replay
→ 提交结果并停止
```

仍不授权：

-生成正式 SIFT10M CP01；
-物化 8M checkpoint-1 数据；
-计算 10K×8M GT；
-clone SIFT10M index；
-80K updates；
-DiskANN stale control；
-5%/10%/20% churn；
-W2/DEEP/GIST。

---

# 7. 输出

提交：

```text
codex/share/2026-07-15/dynamic_vamana_w1_formal_execution_preflight_0715.md
```

报告必须包含：

1. formal/micro artifact map；
   2.修正后的 SIFT10M base realpaths；
2. CP01 filename map；
   4.显式 full-corpus path；
3. clone whitelist；
4. OdinANN uring 编译与 `ldd` 证据；
   7.两次 clean rebuild binary hashes；
5. formal preflight JSON；
   9.修订后 1M replay；
   10.明确声明未执行 SIFT10M CP01/80K。

---

# 8. 最终裁决

统一 formal-path replay 的架构设计已经通过。

但 formal 分支当前仍包含会确定性指向错误数据和错误索引的路径问题，并且 OdinANN artifact 被构建为 AIO。

**当前裁决：REPLAY PASS，SIFT10M HOLD。**
