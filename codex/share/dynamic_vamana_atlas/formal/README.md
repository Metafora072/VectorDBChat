# 三系统 SIFT10M Pilot：F0 审查脚本

本目录仅实现 GPT 批准的 P0 脚本审查项，不启动数据下载、索引构建、tmux 或 W0/W1。

## 脚本顺序

审查通过后，按以下顺序串行运行：

```text
prepare_sift10m.sh
validate_sift10m.sh
f0_diskann.sh
f0_dgai.sh
f0_odinann.sh
```

`prepare_sift10m.sh` 不内置下载站点。操作员必须提供标准 BIGANN/SIFT 的 `.bvecs` 输入，例如：

```text
SIFT10M_BASE_INPUT=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/raw/sift10m/bigann_base.bvecs
SIFT10M_QUERY_INPUT=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/raw/sift10m/bigann_query.bvecs
```

或提供两个显式、可审计的 URL。脚本仅转化前 10,000,000 个 base vectors；不允许复制或重采样 SIFT1M。

## F0 守卫

每个 F0 脚本：

1. 要求数据、checkpoint-0 exact GT 和独立 GT audit 均已完成；
2. 拒绝实验 NVMe 之外的输出和 `TMPDIR`，并要求至少 300 GB 空闲；
3. 验证 DiskANN、DGAI、OdinANN 的固定 commit；源树中仅允许登记的兼容性 patch，且检查 patch SHA256 和反向应用性；
4. 通过 `sudo -n systemd-run --scope --uid=<operator>` 建立 transient dedicated cgroup，并以 `numactl --physcpubind=0-23 --membind=0` 固定 CPU 与 NUMA；每个 phase 保存实际 `taskset`/`numactl --show`；
5. 将 build、load/query 的 wall time、process-tree RSS、cgroup memory、process/cgroup I/O、page-cache 和 allocated/apparent SSD 空间写入 NVMe；
6. 对成功索引设置 immutable base 标记；对失败 attempt 写入 `FAILED`，不覆盖它。重试必须显式设置新的 `F0_ATTEMPT`。

当前主机的无特权 user systemd bus 不可用，故运行前需要由操作员完成 `sudo -v` 或预先配置等价的 root-managed cgroup launcher；脚本使用 `sudo -n`，缺少该前置条件会立即失败而不是回退到共享 session cgroup。

在任何 P1 重型任务之前，先运行 `f0_runtime_canary.sh`。它只写入约 1 MB NVMe 数据并验证独立 scope、operator UID、CPU affinity、`membind`、memory/io cgroup 计数和输出归属。脚本的成功/异常通知通过 `notify_owner.sh` 调用本机 MailSender；可用 `ATLAS_NOTIFY_EMAIL=0` 关闭。

## 结果布局

大文件和运行结果只会写入：

```text
/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/formal/pilot3_sift10m/f0/<system>/<attempt>
/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m/f0/<system>/<attempt>
```

P1 结束后必须停止，以实测下载量、build/load 时间、DRAM、设备 I/O 和索引实际 allocated bytes 修订后续 P2--P4 预算。
