# Dynamic Vamana W1 R03 Preflight Observer-Interference 停止报告

## 结论

R03 continuation 在正式 continuation preflight 的遗留进程检查处 fail closed。停止原因不是 DGAI、OdinANN、DiskANN、CP01 或 GT 异常，而是并发监控命令的参数文本包含 `w1_run_system_canary` 和 `w1_canary`，被当前基于整行命令字符串的正则检查误判为遗留 W1 worker。

停止发生在 preflight 输出、R03 execution manifest、clone target tests、clone、pre-update query 和 update 之前。`results/pilot3_sift10m_w1_r03` 与 `formal/pilot3_sift10m_w1_r03` 均未创建，R02 GT 与 CP01 只有读取，没有写入。依据 R03 失败规则，本轮不自动重试，不复用 R03 名称，也不启动任何后续系统。

## 执行与停止证据

R03 root-owned tmux 于 2026-07-15 18:16:53 UTC 启动。Runtime canary 成功后，preflight 依次执行父状态、GT、CP01、base 和 binary 的只读核验，并在遗留进程检查处于 2026-07-15 18:17:32 UTC 前停止，整体约 39 秒。由于 preflight 采用验证全部通过后才原子创建 result root 的策略，本轮没有生成 R03 result tree 或 execution manifest。

唯一新增的运行证据是项目 NVMe 上的 controller log：

```text
path=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/tmp/pilot3_sift10m_w1_r03_controller.log
size_bytes=6329
sha256=e32beff751641dc83af4acefe2214186a4941eb57a46c1bb20eed4eabc91b944
```

该日志记录了被误判的 PID 与完整命令。停止后 root tmux 和 `dv-w1` scope 均已退出，项目 NVMe 仍有约 1.3 TiB 可用。

## 误判机制

`w1_r03_continuation_preflight.py` 当前从 `ps -eo pid=,args=` 读取整行命令，并使用下列关键词正则搜索任意位置：

```text
w1_canary|w1_run_system_canary|w1_diskann_stale_control|w1_gt_recovery_worker
```

与此同时，Codex 的只读监控命令为了筛选真实 worker，把相同关键词写进 `rg` pattern。虽然监控进程不是 W1 worker，其 `zsh -lc` 参数、Codex sandbox policy 和 `bwrap` argv 中仍包含这些字面量。preflight 排除了自身祖先进程，但监控命令属于并发兄弟进程，因此被加入 `stale_processes` 并触发停止。

该行为说明当前检查证明的是命令行文本包含关键词，而不是进程可执行身份属于 W1 worker。Fail-closed 行为本身正确，身份判定口径过宽。

## R04 建议门禁

建议由 GPT 审议新的 R04 continuation，不在 R03 中续写。最小修复应读取 `/proc/<pid>/cmdline`，仅当独立 argv token 的 basename 精确等于批准的 worker/script 名称时认定为 W1 worker，不再对完整 shell command、JSON policy 或 observer filter 做子字符串搜索。修复必须保留祖先进程排除、tmux/scope 检查和 global flock。

启动前应增加两类回归。第一类构造包含上述关键词的 observer shell/`rg` 参数，要求不会被识别为 worker；第二类使用固定 argv fixture 或受控占位进程呈现精确 worker token，要求仍被拒绝。R04 应使用全新的 result/formal/attempt 名称，重新执行 continuation preflight 与 clone capability tests，只读复用 R02 GT/CP01，并保持 DGAI、OdinANN、DiskANN 串行和任一失败即停止。具体命名与是否授权启动由 GPT 决定。

## 有效性边界

R03 没有产生任何系统结果，因此不能更新 1% churn 的 throughput、visibility、I/O、memory 或 space 结论。此前 R02 GT recovery 通过的结论不受影响，R03 启动前的独立 dry-run 和 clone capability sanity 也仍是有效的基础设施证据，但不能替代一次新的正式 continuation preflight。
