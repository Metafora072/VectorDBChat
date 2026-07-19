# ZNS-ANN Z0A-R2：Final Closure Gate

## 1. 裁决

接受当前 Z0A 的本地裁决：

```text
Z0A = HOLD
Z0B = NOT AUTHORIZED
```

当前结果没有触发方向 KILL：

- DGAI、OdinANN 两个短点均在批准范围内完成；
- 13/13 trace-on 均为零丢失、零失败请求、零序列/时间戳 inversion；
- request → page、accepted application profiler、active set与跨账本 closure 均通过；
- initial-live logical set可恢复；
- host-managed simulator的10个手算case全部通过；
- 主simulator与独立reference逐event一致；
- 空间预算、非系统盘定向和fail-closed cleanup通过；
- 未运行400K、FEMU、synthetic、参数sweep或Z0B。

但当前仍不能判 PASS：

1. DGAI native trace-off/on中位wall time绝对差异为7.51%，超过原5%工程门槛；
2. OdinANN存在约0.2%的原生并发写量波动，不能要求off/on逐run完全相等，也不能仅凭区间重叠直接宣布等价；
3. initial-live manifest尚未编码正式physical packing，正式normalized trace尚未经过独立回读后接入simulator。

因此只批准一次 **Z0A-R2 closure**。R2只补这三项，不扩大工作负载，不判断ANN-specificity。

---

## 2. R2不再使用“多跑几次直到中位数过5%”

禁止通过不断增加重复次数、删除outlier或更换统计口径，使DGAI结果机械低于5%。

R2必须把trace成本拆成三个模式：

```text
NATIVE
  无LD_PRELOAD / 无trace shim

SHIM-CONTROL
  使用与FULL-TRACE相同的函数拦截、FD/object identity解析、
  phase/source识别和固定buffer初始化，
  但不追加record、不写出trace

FULL-TRACE
  完整record append与trace dump
```

目标分别回答：

1. interposition/identity path本身是否改变执行；
2. 实际record capture在相同shim基础上增加多少开销；
3. FULL-TRACE是否改变write structure或并发结果分布。

---

## 3. DGAI timing closure

### 3.1 运行设计

只运行现有SIFT10K、2000 replacement短点。

在固定CPU/NUMA、固定I/O设备、相同clone策略和显式warmup后，执行至少6个随机化triplets：

```text
NATIVE / SHIM-CONTROL / FULL-TRACE
```

triplet内部顺序使用预生成的平衡Latin-square或等价随机顺序，并完整保留所有run。

不得：

- 删除慢run；
- 事后改变warmup；
- 只报告总体中位数；
- 将FULL-TRACE更快解释为优化。

### 3.2 统计对象

以每个triplet内的paired log ratio为主：

```text
log(FULL / SHIM)
log(SHIM / NATIVE)
```

报告：

- 每个paired ratio；
- median；
- 90% bootstrap CI；
- run-order effect；
- wall-time原始值；
- page/request/phase结构。

### 3.3 判定

原5%仍只作为instrumentation工程门槛：

```text
FULL vs SHIM 的90% CI完全位于 [-5%, +5%]
```

则 timing capture PASS。

若FULL vs SHIM未通过，但SHIM vs NATIVE已经产生主要差异，说明问题来自interposition/identity path；允许再做一次实现优化，但不得继续无限迭代。

若经过一次优化仍未通过：

- Z0A temporal-fidelity FAIL；
- 不得使用wall-clock inter-arrival、age-based GC或burst duration；
- 是否保留sequence-only trace由第5节决定。

---

## 4. OdinANN非确定性等价规则

OdinANN不再要求off/on逐run完全相等。其每条FULL trace已经与自己的accepted profiler精确闭合，因此问题是tracer是否系统性改变原生分布。

使用与DGAI相同的三模式triplet设计，至少6个triplets。

对以下指标分别比较：

```text
application bytes
request count
page-event count
insert/repair phase count
unique logical pages
```

判定顺序：

1. NATIVE与SHIM-CONTROL建立原生并发波动范围；
2. FULL-TRACE必须保持零丢失、自账本精确闭合；
3. FULL相对SHIM的paired median shift不能超过NATIVE/SHIM自然波动的尺度；
4. FULL结果不得系统性落在NATIVE与SHIM分布同一侧之外；
5. active set、load/insert/publish phase和source coverage必须继续通过。

报告原始值与paired effect，不使用“p>0.05所以相同”的错误结论。

若FULL造成超出自然波动的系统偏移，则Z0A FAIL；不得以“OdinANN本来就非确定”豁免。

---

## 5. Sequence-only trace的独立判定

Host reclaim的Greedy/OracleMinCopy模型主要依赖write order，而非wall-clock时间。R2必须明确区分：

```text
temporal trace:
  可用于timestamp、inter-arrival、age或burst-duration分析

sequence trace:
  仅用于提交/完成顺序、page-version lifecycle和sequence-based reclaim
```

即使wall-time equivalence未通过，也只有同时满足以下条件，sequence trace才可保留：

1. FULL与SHIM的write bytes、requests、phase counts和active set闭合；
2. DGAI结构精确相等；
3. OdinANN偏移不超过自然并发波动；
4. 多个FULL runs的以下分布稳定：
   - versions per page；
   - sequence reuse distance；
   - per-update write fanout；
   - phase-local page concentration；
   - first/last version sequence span；
5. 未来Z0B对每个系统至少使用多个独立trace realization，而不是单条trace；
6. 不使用age-based victim policy或wall-clock可持续性结论。

若sequence结构本身随tracer发生系统性改变，整个ZNS trace路径KILL。

---

## 6. Formal initial packing closure

### 6.1 Canonical packing

从正式initial-live manifest生成至少一个明确的canonical initial packing：

```text
(file_role, stable_object_id, aligned_offset)
```

排序后顺序装入zones。

必须记录：

```text
page_key
page_bytes
allocated_append_bytes
zone_id
zone_offset
initial_version
```

4 KiB logical-block模型下，partial logical page的append占用如何计算必须明确。不得在logical bytes与allocated bytes之间混用。

### 6.2 Independent readback validator

由与simulator独立的程序重新读取：

- initial manifest；
- generated physical image/map；
- raw trace；
- normalized page events。

验证：

1. 每个initial-live page恰好出现一次；
2. 无page-key collision；
3. zone capacity、open/active与spare约束成立；
4. initial allocated bytes精确闭合；
5. request拆页后的page bytes与raw request闭合；
6. trace中的每个page key可以解析为initial replacement或new page；
7. object incarnation与run identity未跨run复用。

### 6.3 正式短trace replay

DGAI与OdinANN各选择一个FULL trace，经独立validator后接入主simulator和reference simulator。

两实现必须在每个event后对以下状态一致：

```text
logical-to-physical map
current version
zone valid/invalid bytes
write pointer
victim
relocation
reset
HostWA byte counters
```

同时生成final-live manifest，并验证simulator replay后的logical live-page set与最终文件snapshot一致。

本轮只验证closure。即使短trace产生HostWA数值，也不得作为ANN/ZNS研究结论。

---

## 7. Application-write到ZNS append语义

R2必须明确每个application write在模拟ZNS层中的materialization unit：

- 整个4 KiB logical page version；
- 对齐的variable-size log record；
- 或其他明确格式。

不能同时：

- 用application returned bytes作为new logical bytes；
- 又按每个touched page追加完整4 KiB；
- 却不计record/page reconstruction成本。

报告至少包含：

```text
application bytes
normalized logical-page bytes
allocated append bytes
relocation allocated bytes
```

Z0B只能采用一种固定、可实现的materialization semantics。

若现有artifact的sub-page random writes无法在不引入未建模RMW或record-log mapping的情况下映射到ZNS append，ZNS-ANN方向应KILL或重新定义为record-log系统，不能继续称为直接page replay。

---

## 8. R2 PASS条件

同时满足以下条件，Z0A才可PASS：

1. DGAI FULL vs SHIM timing closure通过，或被明确降级为sequence-only且sequence结构稳定；
2. OdinANN FULL没有超出原生并发波动的系统偏移；
3. 两系统FULL trace继续保持零丢失与全部账本闭合；
4. canonical initial packing生成并经独立validator验证；
5. 正式短trace接入主/reference simulator并逐event一致；
6. replay后的final-live logical set与最终snapshot闭合；
7. application-write到ZNS append materialization语义唯一且字节账闭合；
8. 没有运行400K、FEMU、synthetic或Z0B；
9. 报告明确给出：
   - `PASS-TEMPORAL`；
   - `PASS-SEQUENCE-ONLY`；
   - 或`KILL`。

只有前两种才允许提交Z0B scope，且`PASS-SEQUENCE-ONLY`不得使用timestamp/age-based结论。

---

## 9. R2 KILL条件

出现任一项立即关闭当前ZNS-ANN trace方向：

- tracer系统性改变write order/phase/fanout；
- OdinANN FULL偏移超出自然并发波动；
- initial physical image无法从真实snapshot恢复；
- normalized trace无法独立回读并接入simulator；
- final-live set无法与最终snapshot闭合；
- application write无法定义可实现的ZNS append materialization；
- 主/reference replay出现任何逐event分歧；
- 需要继续放宽门槛、删除run或增加任意阈值才能PASS。

---

## 10. 输出与停止点

输出：

```text
codex/share/2026-07-19/
zns_ann_z0a_r2_final_closure_0719.md
```

允许修改：

- Z0A tracer/control mode；
- short-run runner；
- manifest/packing converter；
- independent validator；
- simulator/reference的closure接口；
- Z0A报告与小型evidence。

禁止：

- DGAI/OdinANN 400K；
- Z0B endpoint replay；
- synthetic ANN-specificity测试；
- FEMU；
-参数sweep；
- ZoneEpoch；
-论文写作。

R2完成后停止，不自动进入Z0B。
