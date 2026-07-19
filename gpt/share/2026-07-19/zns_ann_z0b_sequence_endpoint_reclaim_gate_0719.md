# ZNS-ANN Z0B：Sequence-Only Endpoint Reclaim Gate

## 1. 裁决

正式接受 Z0A-R2 的最终结论：

```text
Z0A = PASS-SEQUENCE-ONLY
PASS-TEMPORAL = REJECTED
```

被接受的能力仅包括：

- application write 的完整 sequence；
- stable logical-page identity；
- page-version lifecycle；
- phase、role、update/batch grouping；
- canonical initial packing；
- full-4KiB-page materialization；
- sequence-based host reclamation replay。

以下信息永久禁用于当前 trace：

- wall-clock timestamp；
- inter-arrival time；
- age；
- burst duration；
- time-based Cost-Benefit；
- sustained updates/s；
- cleaning bandwidth随时间；
- wall-clock feasibility或endurance结论。

Z0A-R2 不支持 ANN-specificity，也不支持短点 HostWA 结论。

本轮批准 **Z0B Sequence-Only Endpoint Reclaim**。Z0B只判断真实长序列是否能够形成可重复的多轮 host reclamation 信号，不判断该信号是否为 ANN 独有。

## 2. Z0B 唯一问题

回答：

> 在明确的 initial image、4 KiB page-version materialization 和 sequence-only host cleaner 下，真实 DGAI/OdinANN 长更新序列是否会产生多个完整、可重复的 fill–relocate–reset cycles？

Z0B 不是：

- ZNS feasibility boundary；
- ANN-specificity证明；
- `rho/Gini`因果实验；
- GC policy论文；
- ZoneEpoch设计；
- device-level WA评测。

## 3. 允许的两个端点

只采：

```text
DGAI 50K
OdinANN 400K
```

使用原 M3 对应的 frozen source、dataset、初始index、更新语义与最终active-set定义。报告必须重新写明：

- dataset与维度；
- initial active points；
- replacement/insert/delete数量；
- R、record size和page capacity；
- 文件集合；
- source commit/hash；
- 与M3原点的语义一致性。

两个端点不能放在同一条 `rho -> HostWA` 曲线上，也不能作跨系统线性插值。它们只是低重复控制端点与高重复压力端点。

## 4. Multiple trace realizations

每个系统采集3条独立 FULL sequence trace。

要求：

- 每条从同一immutable initial snapshot的独立clone开始；
- 不使用timestamp分析；
- 保留真实global sequence、phase、role与update/batch identity；
- 每条都执行raw→normalized→packing→main/reference replay完整closure；
- 每条都验证final-live set与真实final snapshot一致；
- DGAI若3条sequence完全相同，照实报告；
- OdinANN保留自然并发产生的独立sequence realizations；
- 任一trace出现drop、账本不闭合、identity collision或final-live不一致，立即停止，不替换该run来凑满3条。

不得只挑选“最典型”的一条trace。

## 5. 空间与运行门禁

启动前提交分项预算：

```text
initial snapshots
6 mutable clones
6 raw traces
6 normalized traces
6 manifests
6 canonical physical maps/images
simulator/reference state
per-cycle output
failure residue
compression temporary
safety margin
```

要求：

- 所有大文件位于 `/dev/nvme8n1` 对应非系统盘；
- free space ≥ 预计peak的1.5倍；
- frozen M0–M3和Z0A artifacts只读；
- cleanup仍使用marker-owned、fail-closed路径；
- 若预计peak超过150 GiB，先停止并提交缩减方案，不直接启动。

不要求保留六份完整sparse physical image；允许使用经独立验证的sparse/map-only representation，但字节账语义必须不变。

## 6. 固定 materialization

沿用R2唯一语义：

```text
每个touched logical page
=> append一个重建后的完整4096-byte page version
```

分别统计：

```text
application returned bytes
normalized fragment bytes
allocated append bytes
replacement RMW read bytes
new-page zero-fill bytes
relocation allocated bytes
```

HostWA定义为：

```text
HostWA
= (allocated append bytes + relocation allocated bytes)
  / allocated append bytes
```

初始image写入不计入更新期HostWA，但必须单独报告。

不得改用variable-size record log来获得更好结果；那属于另一个系统设计。

## 7. Bounded host geometry

Z0B不执行大范围参数sweep，只使用以下透明压力包络：

### Zone capacity

```text
256 MiB
1 GiB
```

### Host spare zones

```text
2 zones
8 zones
```

对每个配置：

```text
ordinary initial zones
= canonical initial image实际占用zones

total zones
= ordinary initial zones + host spare zones
```

### Open/active语义

采用单append-head模型：

```text
max_open_zones = 1
max_active_zones = total zones
```

这四个配置只用于判断信号是否存在及对geometry是否脆弱，不代表“行业标准”或真实设备最优配置。

若某端点的initial image连一个ordinary zone都无法稳定定义，停止。

## 8. Initial placement sensitivity

每条真实trace至少比较：

1. `Canonical`
   `(file_role, stable_object_id, aligned_offset)`排序。

2. `RoleSeparated`
   不同file role从不同zone边界开始；role内部保持canonical顺序。

3. `RandomPacking`
   3个预登记固定seed。

4. `OfflineHotColdOracle`
   利用完整未来sequence按page rewrite count排序，仅作为不可在线实现的下界参照。

Oracle不能作为系统baseline或贡献。

如果Canonical、RoleSeparated与Random之间的结果范围比系统/端点差异更大，应判为placement-dominated，不得写成ANN update强结论。

## 9. Cleaner

只使用：

- `GreedyValidFraction`
- `OracleMinCopy`

`OracleMinCopy`仍仅在当前eligible victims中选择copy bytes最少的zone，不看未来。

如果两者在当前FULL-only candidate语义下完全相同，作为sanity结果报告，不制造虚假的policy contribution。

不使用：

- age-based Cost-Benefit；
- temperature estimator；
- ANN-aware cleaner；
- learned policy；
-任意watermark。

回收只在下一次append无法完成时机械触发。

## 10. Exact-order replay输出

每个：

```text
system × trace realization × geometry × placement × cleaner
```

报告：

```text
allocated new append bytes
relocated bytes
HostWA
reset count
victim valid-fraction sequence
relocated pages per cycle
free-zone count per event/cycle
live/invalid bytes per cycle
cycle start/end sequence number
page-role composition of victims
update/batch IDs crossing each cycle
```

不得转换为秒、MB/s、updates/s或age。

## 11. Multi-cycle与sequence-stability判定

### 11.1 Cycle eligibility

只有完成：

```text
victim selection
live-page relocation
zone reset
reset zone重新进入free pool
```

才计为一个完整cycle。

未完成的尾部cycle不计入稳态统计，单独报告tail state。

### 11.2 高压力端点

OdinANN-400K在至少一个非Oracle placement、至少一个zone capacity和两种spare设置之一中，必须完成至少8个完整cycles。

若所有透明geometry下均少于8个cycles：

```text
KILL-NO-RECLAIM-SIGNAL
```

不得循环复制trace制造cycle。

### 11.3 低压力端点

DGAI-50K允许：

- 不触发GC；
- 只触发少量cycles；
- 或形成稳定cycles。

它只作为低重复控制，不要求与Odin同样数量。

### 11.4 稳定性

对Odin符合cycle数量的配置，按cycle报告：

```text
HostWA_cycle
relocated_pages_cycle
victim_valid_fraction
```

使用预登记的sequence-index趋势检查：

- 对后半cycles计算Theil–Sen slope；
- block bootstrap 90% CI；
- CI包含0才标为`NO-DETECTED-SEQUENCE-TREND`；
- CI不包含0标为`NONSTATIONARY`。

这里的stationary只指cycle index上的sequence统计，不是wall-clock steady state。

至少一个Canonical或RoleSeparated配置必须达到：

```text
>=8 complete cycles
AND NO-DETECTED-SEQUENCE-TREND
```

否则不得进入ANN-specificity阶段。

## 12. Cross-realization复现性

不要求Odin三条trace逐event相同。

必须报告每个配置在三条trace上的：

```text
HostWA range
reset-count range
median victim valid fraction range
per-cycle relocated-page distribution distance
```

通过条件：

- 三条trace对“是否形成>=8 cycles”的判断一致；
- Canonical与RoleSeparated的相对高低方向不发生任意反转，或明确判为不稳定；
- 不能由单条trace独占全部reclaim信号；
- DGAI结果不因某一条trace突然产生完全不同regime。

不使用任意`15%`差异阈值。

## 13. Z0B结果分类

最终只能给出以下之一。

### PASS-RECLAIM-SIGNAL

同时满足：

1. 六条trace全部closure通过；
2. Odin在非Oracle配置形成>=8完整cycles；
3. 至少一个Canonical/RoleSeparated配置后半cycles无检测到sequence趋势；
4. 三条Odin realization对cycle存在性与主要范围一致；
5. 结论不依赖单个random packing；
6. materialization、HostWA和tail账完整；
7. 不使用temporal信息。

PASS只表示：

> 真实ANN update sequence足以驱动可重复host reclamation。

它不表示ANN-specific，不授权ZoneEpoch或论文。

### HOLD-PLACEMENT-DOMINATED

出现：

- 是否GC或HostWA主要由initial packing决定；
- Canonical/RoleSeparated/Random结论大幅反转；
- Oracle与现实placement差距极大；
- 多realization regime不稳定。

该结果只允许提交placement/lifecycle解释，不自动继续。

### KILL-NO-RECLAIM-SIGNAL

出现：

- Odin-400K在透明geometry下无法形成足够cycles；
- cycle统计持续单调漂移且trace结束前不稳定；
- exact replay无法闭合；
- 只能通过循环trace、缩小到toy zone或减少到病态spare空间制造GC。

## 14. Z0B明确不做的事情

禁止：

- synthetic uniform/Zipf/temporal-clustered baselines；
- ANN-specificity claim；
- Gini或`rho`因果回归；
-跨系统boundary；
- `WA=3`；
-device WA；
- FEMU；
- real ZNS hardware；
- GC policy优化；
- ZoneEpoch；
- query/read-path实验；
-论文写作。

只有`PASS-RECLAIM-SIGNAL`后，才允许另行提出Z0C matched-baseline/ANN-specificity gate。

## 15. 输出与停止点

输出：

```text
codex/share/2026-07-19/
zns_ann_z0b_sequence_endpoint_reclaim_0719.md
```

报告必须包含：

- 六条trace provenance与closure；
- peak-space实际值；
- 全部geometry/placement/cycle结果；
- per-cycle sequence趋势；
- cross-realization范围；
- `PASS-RECLAIM-SIGNAL / HOLD-PLACEMENT-DOMINATED / KILL-NO-RECLAIM-SIGNAL`；
- 若PASS，仅给Z0C可能回答的问题，不执行。

完成后停止，不自动进入Z0C。
