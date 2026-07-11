# Claude 当前立场

日期：2026-07-12，最后更新 04:13 (UTC+8)

## 已确认的 KILL（共 8 个方向）

1. M08 Stable-ID Refresh
2. Dir 1 Deferred Topology Writes
3. Append-only 邻接表版本化
4. Coordinate acquisition/rerank 优化
5. DGAI 单系统 profiling
6. 维护债务观测（候选二）
7. Write-set constrained relayout
8. 并发 query/update SSD 干扰（候选 A）

## 当前活跃方向

**软件栈瓶颈（PZ 提出，Claude 评估为最有系统味道）**

核心假设：现代高带宽 SSD 下，驻盘图索引的瓶颈已从设备转移到软件栈。IISWC 2025 测得 DiskANN 仅利用 SSD 24% 带宽。WSBuffer (FAST 2026) 在通用 I/O 上验证了类似论断。图索引的 dependent-read 模式需要专门的 I/O + 搜索算法 co-design。

Novelty 边界：VeloANN/LIOS 优化 CPU 利用率（非 I/O 栈）；Turbocharging 用 io_uring 但针对 IVF；WSBuffer 是通用 write path。没有等价工作。

状态：**等待 Problem Gate P0** — 在 DGAI 上分解 per-I/O 时间为软件栈 / 设备 / CPU 计算。软件栈占 30%+ 则 Continue，否则 Kill。

详见 `claude/share/claude_software_stack_direction_0712.md`。

## 下次介入条件

P0 结果出来后，判断方向是否成立并审查系统假设。
