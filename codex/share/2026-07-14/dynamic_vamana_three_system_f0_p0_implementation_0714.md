# 三系统 SIFT10M Pilot：P0 脚本实现与审查入口

**状态：** P0 代码已准备并完成静态检查；未下载数据、未创建 tmux、未启动 build/query。
**依据：** `gpt/share/dynamic_vamana_three_system_pilot_amendment_0714.md`。
**范围：** DiskANN、DGAI、OdinANN 的 SIFT10M 数据准备与 F0 readiness；不含 Fresh-Ref、W0、W1、DEEP10M、GIST1M 和 W2。

## 新增入口

| 入口 | 职责 | 运行前提 |
| --- | --- | --- |
| `prepare_sift10m.sh` | 取得经操作员指定的标准 BIGANN `.bvecs`、转化前 10M、生成 80/20 与 checkpoint 数据、hash | 明确的本地输入或 URL；无默认下载站点 |
| `validate_sift10m.sh` | 仅计算并独立审计 checkpoint-0 exact GT | 已完成数据准备 |
| `formal/f0_diskann.sh` | DiskANN build、load/query smoke、资源/空间记录、immutable base | 数据与 checkpoint-0 GT 已验证、dedicated cgroup 可用 |
| `formal/f0_dgai.sh` | DGAI 同上，含 8M postprocess | 同上 |
| `formal/f0_odinann.sh` | OdinANN 同上 | 同上 |

三份 F0 脚本是三个独立入口，公共守卫位于 `formal/f0_common.sh`。每份脚本使用系统自身的 build/search 工具与既有 1M 参数体系；F0 query 以 `L=40` 做单点 load/query smoke，P2 才扫描四个 search settings。

## 已实现的门禁

1. 所有写入路径和 `TMPDIR` 必须在 `/home/ubuntu/pz/VectorDB/data`；低于 300 GB 可用空间即失败。
2. 数据来源只能是标准 `.bvecs`；脚本只截取前 10M，不接受 SIFT1M 复制/重采样。原始 source bytes、转换文件 bytes、SHA256 与显式 URL 会记录到 NVMe manifest。
3. 每个 F0 运行核对固定 source commit，并验证三个 compatibility patch 的 SHA256、允许修改文件集和 `git apply --check --reverse`。静态测试已在当前三套源码上通过。
4. 每个 build/query 通过 root-managed transient `systemd-run` scope 启动，固定 CPU `0-23`/NUMA node 0，记录 process-tree RSS、`smaps_rollup`、cgroup memory、process/cgroup I/O、page-cache、allocated/apparent SSD 字节和 `/usr/bin/time -v`。
5. 成功索引只在 build 与 query 均完成后标记 `F0_OK`，并设置 immutable-base 标记。任一失败写入 `FAILED`；同一 attempt 不能静默覆盖，重试必须使用新的 `F0_ATTEMPT`。
6. P1 完成后流程停止，不会自动进入 P2/P3/P4。P3 的 1% canary 也尚未实现或授权启动。

## 已完成的静态验证

| 检查 | 结果 |
| --- | --- |
| `bash -n`：两份数据脚本、公共守卫、三份 F0 脚本 | 通过 |
| `python3 -m py_compile`：数据、GT、资源和 BVec 转换工具 | 通过 |
| BVec→FBin 转换小样本（2D、2 rows） | 通过 |
| DiskANN/DGAI/OdinANN commit + allowed-patch guard | 通过 |
| `git diff --check` | 通过 |

## 需要审查的运行前置条件

当前主机无可用的 unprivileged user systemd bus。为避免伪造 dedicated cgroup，F0 脚本使用 `sudo -n systemd-run --scope --uid=<operator>`，在没有预认证或 root-managed launcher 时会立即失败，而不会回退到共享 login cgroup。正式启动前，操作员需要先完成 `sudo -v` 或等价的 cgroup launcher 配置；这不是脚本自动绕过的事项。

审查通过后的唯一许可顺序是：数据准备 → checkpoint-0 GT validation → DiskANN F0 → DGAI F0 → OdinANN F0。每一步完成后保留实际时间、空间、DRAM 和 I/O 记录，三系统 F0 全部完成后再回到对话修订 P2--P4 预算。
