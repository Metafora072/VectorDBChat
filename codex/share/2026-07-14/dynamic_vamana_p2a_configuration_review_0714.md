# Dynamic Vamana P2-A 校准完成与配置复核请求

## 审阅请求

P2-A 已于 2026-07-14 完成 3 个系统、每系统 7 个 `Tq=1` 校准点，共 21 个结果点。根据 Gpt 的 P2 授权门禁，只有至少 2 个共同 Recall@10 目标可被三系统覆盖时，才可进入 P2-B 的 W0 测量。当前汇总文件中的 `common_targets` 为空，因此 P2-B 未启动。请 Gpt 复核本次校准是否应按“配置不可比”处置，并决定是否允许一次受限的校准修复；在此之前，禁止进入 W0、W1 或 churn 阶段。

原始汇总位于 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_p2/calibration_summary.json`，逐点记录位于同目录的 `calibration.tsv`，控制器完成标记为 `p2_controller/P2_CALIBRATION_COMPLETE`。

## 完成范围与运行完整性

资源 `memory.events` canary 已通过。每个校准点均使用独立 transient cgroup，记录了 `memory.events`、峰值内存、NVMe 读取字节、进程树 RSS、驱动报告 QPS 及外部计时。所有记录点的 `returncode` 均为 0，且 DGAI 的已完成点未出现 cgroup OOM 事件。

DGAI 的冻结索引与原生查询实现存在只读兼容性缺陷。其查询加载起初把主索引、坐标文件和图文件以 `O_RDWR` 打开，因而在 F0 的 `chmod -R a-w` 后无法由独立进程查询。修复使查询调用链在 `enable_writes=false` 时使用 `O_RDONLY`，保留更新路径的可写打开方式。修复、来源白名单与安全续跑逻辑已推送至 chat 仓库的 `0ce53dc`、`b876277`、`9827ca3`；失败的 `DGAI/L20/r1`、`r2`、`r3` 均保留，成功的读取仅写入新的 `r4` 目录。

## 校准结果

| 系统 | L=20 | L=40 | L=80 | L=120 | L=160 | L=240 | L=320 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DiskANN Recall@10 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| DGAI Recall@10 | 0.8424 | 0.9187 | 0.9622 | 0.9775 | 0.9857 | 0.9921 | 0.9950 |
| OdinANN Recall@10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

DGAI 呈现合理的 Recall–成本单调上升关系。例如，L=20 至 L=320 时，Recall@10 从 0.8424 升至 0.9950，QPS 从 1780.76 降至 412.62，平均 I/O 数从 56.24 升至 342.81。DiskANN 在全部候选 L 上均为 1.0000，无法为 0.93–0.99 任一目标提供低侧 bracket。OdinANN 的每个点均给出 0 Recall，同时仅约 0.047–0.054 秒完成 2,000 个查询、每查询平均 1 个 I/O，明显不符合与另两系统相同的真实检索工作量。

更关键的是，OdinANN 的每个原始 `driver.log` 均含大量 `Failed Bad file descriptor`，例如 `raw/OdinANN/tq1/L320/r1/driver.log`。现有 aggregate validator 未把该文本列入 fatal marker，因而错误地生成了 `returncode=0`、`fatal_markers=false` 的点记录。该 7 个 OdinANN 点不能作为有效 Recall 或性能证据。

## 门禁结论

P2-A 的校准执行已完成，但校准配置不具备三系统可比性：DiskANN 的候选网格饱和，OdinANN 的结果无效，因而共同目标数为 0。这个状态不是 P2-B 的失败结果，而是 P2-A 的配置复核触发条件。不得把 OdinANN 的 0 Recall 或极高 QPS 用作系统结论。

建议 Gpt 在以下两种处置中选择其一。第一，授权一次受限配置修复，仅修复 OdinANN 查询有效性、扩展 DiskANN 的低 L 候选，并对修复后的系统重新做 `Tq=1` 校准；既有 21 点和全部失败证据保持不变。第二，判定三系统共同 Recall 校准在当前二进制/网格下不可成立，关闭 P2 而不执行 W0。无论选择何者，都不应自动触发 P2-B。
