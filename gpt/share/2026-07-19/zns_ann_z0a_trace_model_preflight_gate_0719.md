# ZNS-ANN Z0A：Trace / Model Preflight Gate

## 1. 最终裁决

Claude 对原提案的五项修正接受，但提交的 `zns_z0_scope_0719.md` **不按原方案批准执行**。

当前方案仍存在以下拒绝级问题：

1. 只采 DGAI-400K 单点，无法建立低重复与高重复端点，也无法判断结果是否属于 DGAI 实现、特定规模或 ANN workload；
2. `(sequence_number, page_id, write_size)` 缺少稳定对象身份、文件角色、phase、batch/update identity，无法恢复真实 logical-page lifecycle；
3. 未定义 initial live image、logical-to-physical mapping、open/active zone限制与 host spare zones，不能正确计算 victim valid fraction；
4. 512 MiB zone、14% OP 与单一 Greedy policy仍是未证明的任意配置；
5. Uniform/Zipfian/temporal-clustered 三种生成器并非 strongest matched generic baselines；
6. real trace 与三个synthetic相差 `>15%` 只能证明这些生成器不充分，不能证明差异是 ANN-specific；
7. `<15%` 也不能证明 `rho` 足以预测 GC，因为单配置可能掩盖时序差异；
8. `15%` 本身是任意阈值；
9. 未要求多个完整 fill–clean–reset cycles与窗口稳态；
10. 未建立 simulator conservation oracle与独立reference实现；
11. 30 GiB 只是估计，没有分项峰值、失败残留和清理闭合。

因此本轮只批准 **Z0A preflight**。Z0A 不运行 DGAI-400K 或 OdinANN-400K，不采百万级完整 trace。

---

## 2. Z0A 唯一目标

回答：

> 能否以低扰动、可闭合的方式，从现有 DGAI/OdinANN artifact 采集足以驱动 host-managed ZNS replay 的完整 page-version trace，并建立一个在手工实例上正确的 host-reclamation simulator？

Z0A 只验证测量与模型能力，不判断 ANN-specificity，不判断 ZNS-ANN 是否值得立项。

---

## 3. Trace schema

每个原始 application write 至少记录：

```text
global_seq
thread_seq
monotonic_timestamp_ns
system
run_id
device_id
stable_object_id
inode
file_role
phase
source_entrypoint
offset
length
update_or_replacement_id
batch_id
```

规范化为4 KiB page events时，还需记录：

```text
request_id
page_key = (stable_object_id, aligned_page_offset)
page_index_within_request
page_bytes
```

要求：

- 同一文件不同run不能错误复用object identity；
- 不同文件相同offset不能冲突；
- load、insert、repair、publish、shadow-copy等phase可区分；
- 原始request与拆分page event可双向闭合；
- 每个logical page version能确定前一current version何时失效。

仅有`page_id`或offset不通过。

---

## 4. Instrumentation preflight

### 4.1 小规模运行

仅运行现有最小/短规模路径，目标是产生：

```text
10^4–10^5 write events
```

不得运行400K完整点。

DGAI与OdinANN各运行一次短点，用于验证两种I/O engine和文件集合都能被相同schema覆盖。

### 4.2 低扰动门禁

分别运行：

```text
trace-off
trace-on
```

每种至少重复3次，报告：

- wall time；
- application bytes；
- request count；
- page-event count；
- phase counts；
- output checksum / active-set checks；
- trace buffer peak RAM；
- dropped events；
- timestamp/sequence inversions。

通过条件：

- `0` dropped events；
- bytes与accepted profiler精确闭合；
- request拆分前后精确闭合；
- trace-on不改变写入数量与phase结构；
- wall-time中位数扰动不超过5%，否则需改用更低开销buffer后重测。

5%仅作为instrumentation perturbation工程门槛，不作为论文结论。

---

## 5. Initial image闭合

ZNS replay前必须生成 initial-live manifest：

```text
stable_object_id
file_role
logical_page_key
initial_version
record/page bytes
initial_live flag
```

明确：

- replay开始前哪些页面已经存在；
- 哪些文件属于长期索引；
- 哪些是临时、shadow、publish或load副本；
- initial packing如何产生；
- update trace中的第一次write是new logical page还是旧页replacement。

若无法从artifact与snapshot恢复initial live set，ZNS replay方向直接KILL；不能假设空设备开始。

---

## 6. Host-managed simulator preflight

### 6.1 固定语义

先实现最小模型：

```text
zone_size_bytes
zone_capacity_bytes
logical_block_size
number_of_zones
max_open_zones
max_active_zones
host_spare_zones
```

不得使用抽象OP百分比代替实际zone数量。

状态至少包含：

```text
logical_to_physical_map
zone_write_pointer
valid_bitmap_or_exact_live_set
invalid_bytes
open/active state
relocation destination
reset state
```

### 6.2 回收触发

只允许机械触发：

> 下一次append无法在满足open/active约束的可用zone中完成。

不得使用任意“两空zone”水位。

### 6.3 两个策略

- `GreedyValidFraction`
- `OracleMinCopy`：仅作为当前候选zone中的sanity upper bound

不实现Cost-Benefit、age分数或ANN-aware policy。

### 6.4 必须满足的invariants

```text
每个logical key最多一个current live version
reset前zone中live bytes为0
write pointer单调且不超过capacity
relocation不改变logical version
open/active zone限制始终成立
HostWA = (new logical bytes + relocated live bytes) / new logical bytes
```

字节账必须在每个event后闭合。

---

## 7. 手工与独立oracle

至少构造以下可手算trace：

1. 全部new writes：HostWA=1；
2. 同一page连续重写；
3. hot pages集中在单zone；
4. hot/cold混合；
5. relocation产生二次空间压力；
6. 多文件相同offset；
7. 跨页write；
8. active/open zone限制触发；
9. victim中仍有live pages时的迁移；
10. reset后zone重新使用。

主simulator必须与：

- 手工结果；
- 一个独立的简化reference implementation

逐event一致。

---

## 8. 空间预算

启动前报告分项峰值：

```text
base index/snapshot
trace binary
trace RAM buffer
initial manifest
normalized event file
simulator state
simulator output
temporary compression
failure residue
safety margin
```

所有大文件定向到非系统盘。

通过条件：

- 明确目标挂载点；
- 启动前free space大于预计峰值的1.5倍；
- 提供正常完成与异常失败的清理脚本/清单；
- 不覆盖M0–M3 frozen artifacts。

---

## 9. Z0A PASS条件

同时满足才允许提交Z0B endpoint replay计划：

1. DGAI与OdinANN短点均由统一schema完整覆盖；
2. trace无丢失并与physical/application账本闭合；
3. instrumentation扰动可接受；
4. initial live image可恢复；
5. simulator全部conservation invariants通过；
6. 手工oracle与独立reference逐event一致；
7. host/device WA语义明确分离；
8. peak-space预算闭合；
9. 没有运行400K、FEMU或synthetic ANN-specificity实验。

---

## 10. Z0A KILL条件

出现任一项立即关闭ZNS-ANN：

- 无法获得稳定object/page identity；
- initial live set无法恢复；
- trace无法覆盖异步I/O completion与实际write顺序；
- instrumentation明显改变workload；
- application trace无法与物理写账闭合；
- host mapping内存开销在目标规模明显不可接受且无可行分层方案；
- simulator无法通过独立oracle；
- replay只能从空设备开始才能工作；
- 必须使用任意阈值或特定synthetic生成器才能产生结论。

---

## 11. Z0B预留边界

Z0A PASS后，Z0B才允许采：

```text
DGAI-50K
OdinANN-400K
```

两个端点。

Z0B不会以`real vs 三个synthetic >15%`作为PASS条件。它将：

- 使用exact-order replay；
- 检查至少3个完整reclaim cycles；
- 做window stability与initial-placement sensitivity；
- 构造逐项匹配working set、bytes、burst size、phase lengths和reuse-distance的generic baselines；
- 将“rho不充分”与“ANN-specific结构”分开判断。

Z0A完成前不编写Z0B完整实验矩阵。

---

## 12. 输出与停止点

输出：

```text
codex/share/2026-07-19/
zns_ann_z0a_trace_model_preflight_0719.md
```

完成后停止，不自动进入Z0B。

本轮禁止：

- DGAI-400K完整采集；
- OdinANN-400K完整采集；
- 30 GiB trace；
- synthetic baseline结论；
- 15% PASS/KILL；
- FEMU；
- 参数sweep；
- ZoneEpoch；
- 论文写作。
