# 三系统 SIFT10M Pilot：P0 脚本审查

**日期**：2026-07-14
**审查对象**：`codex/share/dynamic_vamana_three_system_f0_p0_implementation_0714.md`
**对应提交**：`d71b85bcd9eeaeeaadc2bc5a72e56dad6623aaaf`
**裁决**：**REVISE — 修订并完成运行时 canary 后才允许进入 P1**

---

## 1. 总体评价

P0 的整体执行结构是正确的：

* DiskANN、DGAI、OdinANN 使用独立 F0 入口；
* 数据、索引、结果和临时文件限制在实验 NVMe；
* 固定并检查 source commit；
* compatibility patch 具有 SHA256 与允许文件集合；
* build、query 和失败 attempt 分离；
* dedicated cgroup 不可用时拒绝回退；
* P1 完成后不会自动进入 W0/W1；
* 当前没有下载 SIFT10M，也没有启动正式实验。

这些设计可以保留。

但当前实现仍有四项必须修改的问题，其中 NUMA 绑定和数据 provenance 属于正式实验正确性问题，不能只作为 caveat 记录。

---

# 2. R1：真正实施 NUMA 绑定

## 当前问题

脚本定义并记录：

```text
CPUSET=0-23
NUMA_NODE=0
```

但实际运行只向 systemd scope 设置：

```text
AllowedCPUs=0-23
```

没有实施：

* memory binding；
* NUMA-node binding；
* CPUSET 与 node 0 的一致性检查。

因此当前只能声称限制了可运行 CPU，不能声称固定了 NUMA node 0。

## 必须修改

在 preflight 中：

1. 验证 `node0` 存在；
2. 读取 `/sys/devices/system/node/node0/cpulist`；
3. 验证请求的 CPUSET 与目标 NUMA node 一致；
4. 检查 `numactl` 可用。

正式命令至少通过以下方式之一执行：

```text
numactl
  --physcpubind=<CPUSET>
  --membind=<NUMA_NODE>
```

建议将 `numactl` 放在 `resource_probe.py` 外层，使 probe 及其所有子进程都继承相同 CPU 与内存策略。

若当前 systemd 支持，也可以同时设置 cgroup 的 memory-node 限制，但不能仅依赖未经运行验证的 property。

environment manifest 额外保存：

```text
numactl --show
node<N>/cpulist
effective cpuset
effective memory nodes
```

---

# 3. R2：补齐 SIFT10M 数据 provenance

## 当前问题

`.bvecs` 后缀、128 维和文件长度只能证明文件结构合法，不能证明它就是标准 BIGANN/SIFT 数据。

当前 preparation manifest 只记录：

* source path；
* source URL；
  -文件大小；
  -转换文件大小。

但没有记录：

* base source SHA256；
* query source SHA256；
* canonical 10M fbin SHA256；
* canonical query fbin SHA256；
  -与可信预期 hash 的比较结果。

## 必须修改

`prepare_sift10m.sh` 在转换前后必须计算：

```text
base_source_sha256
query_source_sha256
base_10m_fbin_sha256
query_fbin_sha256
```

同时支持：

```text
SIFT10M_BASE_EXPECTED_SHA256
SIFT10M_QUERY_EXPECTED_SHA256
```

若提供 expected hash，任何不匹配必须立即停止。

如果上游没有公开 checksum，也必须：

1. 保存明确的下载 URL；
2. 保存实际 SHA256；
3. 在 manifest 中标记 `expected_hash_available=false`；
4. 在启动数据准备前由人工确认 URL 是认可的标准 BIGANN 来源。

不能仅凭脚本成功就自动将 corpus 标记为“标准 BIGANN”。

还需避免以下情况：

* `.partial` 来自旧 URL，却被新 URL 继续下载；
  -本地输入文件在两次运行间被替换；
  -转换文件已存在，但其 source hash 已改变。

因此已有 canonical 文件的复用必须同时核对 source hash 和 conversion manifest。

---

# 4. R3：增加 dedicated cgroup 运行时 canary

## 当前问题

静态检查无法证明以下链路在当前主机上成立：

```text
sudo -n
→ systemd-run --scope
→ --uid=<operator>
→ dedicated cgroup
→ resource_probe 读取 memory/io
→ 用户拥有输出文件
→ scope 正常回收
```

正式下载和构建前必须先验证这条链路。

## 新增入口

建议新增：

```text
formal/f0_runtime_canary.sh
```

canary 只运行数秒，执行：

1. 在 NVMe 临时目录写入一个小文件；
2. 分配一小段可观测内存；
3. 记录 PID、UID、CPU affinity 和 NUMA policy；
4. 由 `resource_probe.py` 采集；
5. 正常退出。

## Canary 必须证明

* command UID 是 `ubuntu`，而不是 root；
  -输出文件归操作员所有；
* `cgroup_path` 是新建的独立 scope，不是 login/session cgroup；
* `memory.current` 和 `memory.peak` 非空；
* `io.stat` 至少包含实验 NVMe 对应的 major:minor；
* CPU affinity 符合 CPUSET；
* NUMA memory policy 符合 NUMA_NODE；
* resource report 能正常落盘；
  -命令退出后 scope 可以被 systemd 回收；
  -缺少 `sudo -v` 时脚本按预期 fail-fast。

canary 报告中应保存：

```text
systemd unit name
cgroup path
effective UID/GID
effective CPU affinity
effective NUMA policy
memory.current/peak
io.stat
output ownership
exit code
```

在 canary 通过前，不启动 10M 数据准备。

---

# 5. R4：加强路径、空间和查询正确性守卫

## 5.1 数据准备空间守卫

当前 300 GB 空闲检查只存在于 F0 common launcher。

`prepare_sift10m.sh` 在下载或转换 128 GB source 前也必须执行相同检查，否则可能在到达 F0 前就占满设备。

建议数据准备至少要求：

```text
available NVMe space >= 300 GB
```

并在以下阶段重新检查：

-下载前；
-转换前；
-checkpoint 物化前。

---

## 5.2 使用真实路径与挂载设备验证

当前路径检查是字符串前缀检查：

```text
/home/ubuntu/pz/VectorDB/data/*
```

它不能防止目录中的 symlink 指向系统盘或其他挂载点。

需要：

1. 对已有路径执行 `realpath`；
2. 对即将创建的路径验证最近存在的父目录；
3. 使用 `findmnt -T` 确认路径位于预期实验 NVMe；
4. 记录目标 block device major:minor。

源码输入可以是只读外部路径，但所有下载文件、canonical 数据、GT、index、result 和 TMPDIR 必须落在已验证的 NVMe mount 上。

---

## 5.3 强化 query readiness 验收

当前只检查日志中存在 `Recall@10` 和数字行，不足以证明结果正确。

F0 query 后至少验证：

* Recall 可解析；
* Recall 为有限数；
* Recall 位于 `[0,1]`；
* query 数量等于预期；
  -每条 query 返回 K 个结果；
  -结果 ID 均属于 checkpoint-0 active tag 集；
  -不存在非法 sentinel、越界 ID 或损坏结果文件；
  -系统进程返回码为 0。

可以复用准备阶段的结果解析器，或新增统一的：

```text
validate_query_result.py
```

三个系统必须使用相同的逻辑验收条件。

F0 不要求达到某个高 Recall，但不能接受无法解析或明显错误的结果。

---

# 6. 修订后的授权顺序

当前只授权 Codex：

1. 修正 R1–R4；
2. 新增并运行 lightweight cgroup/NUMA canary；
3. 输出 canary 证据；
4. 更新 P0 审查报告。

输出路径：

```text
codex/share/dynamic_vamana_three_system_f0_p0_revision_0714.md
```

报告必须包含：

-修改文件；
-静态检查；

* source/canonical hash schema；
  -NUMA 实施方式；
  -cgroup canary 原始结果；
  -目标 NVMe major:minor；
  -查询结果 validator；
  -仍未启动正式数据下载和 F0 的声明。

在 Gpt/Claude 确认前，仍不授权：

-下载完整 BIGANN；
-物化 SIFT10M；
-计算 8M exact GT；
-构建三个正式索引；
-启动 tmux；
-执行 W0/W1。

---

# 7. 最终裁决

P0 的设计框架可保留，但当前实现尚不足以进入 P1。

本轮不是重新设计实验，而是确保：

```text
输入数据可追踪
+ NUMA 约束真实生效
+ dedicated cgroup 真实可用
+ query readiness 具备语义验证
```

这四项一旦通过，三系统 SIFT10M Pilot 即可开始数据准备和 F0。
