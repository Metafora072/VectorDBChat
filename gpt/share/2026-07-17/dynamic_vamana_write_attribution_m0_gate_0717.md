# Dynamic Vamana：Write Attribution M0

## 1. 目标

定位 OdinANN 较高持久化写入量的真实来源，并判断主要成本来自：

* delete；
* insert；
  -邻居图修复；
  -metadata/tombstone；
  -publish/save；
  -其他实际写入路径。

本轮仅做机制归因，不设计新系统，不提前提出优化方案。

## 2. 已知证据

CP20 阶段：

| System  | Ingest write | Publish write |
| ------- | -----------: | ------------: |
| DGAI    |   30.708 GiB |     5.086 GiB |
| OdinANN |  137.194 GiB |     7.629 GiB |

OdinANN 相对 DGAI 的主要写入差距发生在 ingest path。Publish/save 暂不作为首要怀疑对象。

## 3. 第一阶段：源码审计

检查 OdinANN 与 DGAI 的真实更新调用链，输出：

```text
codex/share/2026-07-17/
dynamic_vamana_write_attribution_m0_0717.md
```

必须明确：

1. replacement 中 delete、insert、neighbor repair、metadata update、save/publish 对应的函数与调用关系；
2. 各步骤可能修改的真实文件或文件区域；
3. OdinANN 在什么时点建立 online visibility；
4. online visibility 建立前必须完成哪些内存或持久化操作；
5. DGAI ingest 生成什么 delta 状态；
6. DGAI 为什么必须 publish/reload 后才能由当前 query path 读取；
7. 可以低侵入增加聚合计数的 write、pwrite、io_uring 或内部写入入口。

所有结论必须来自实际代码与文件打开路径，不得只根据论文描述或文件名推测。

## 4. 第二阶段：100K Pilot

源码审计完成后，允许自动运行最小 profiling pilot。

### 输入

两个系统分别：

* 从 R12 frozen CP10 source 创建 fresh private clone；
* 使用相同 replacement trace：
  `[800000:900000]`；
* replacement 数量为 100K；
  -不得修改 R12、R13 frozen clone或历史结果。

### Instrumentation

使用独立 instrumented binary。

Instrumentation 只在内存中聚合，阶段结束后一次性输出 summary，不允许逐操作写日志。

至少记录：

### 按 phase

* delete；
  -insert；
  -neighbor repair；
  -metadata；
  -publish/save；
  -other。

### 按 component/file

根据实际代码区分：

* graph；
  -vector；
  -delete/tombstone；
  -metadata；
  -other。

### 指标

* application-requested write bytes；
  -write调用次数；
  -触及的唯一4KiB page数；
  -同一page累计写入次数；
  -page rewrite factor；
  -fsync/fdatasync次数；
  -cgroup NVMe read/write bytes；
  -ingest、publish、end-to-end wall time；
  -active-set exact；
  -online/fresh visibility；
  -query smoke。

Instrumented binary只用于归因，不与原始binary进行正式性能排名。

## 5. Pilot 通过条件

必须同时满足：

1. replacement数量与区间正确；
2. active set exact；
3. visibility和query smoke正确；
4. frozen source未变化；
5. 至少90%的application-level write bytes能归入明确phase与component；
6. device write为正，且与application归因方向一致；
7. 无OOM、fatal或索引异常。

如果覆盖率不足90%，停止并报告未覆盖的write path，不扩大实验规模。

## 6. 第三阶段：固定与边际成本

仅在100K pilot通过后执行，优先只测试OdinANN：

| Size | Trace prefix       |
| ---: | ------------------ |
|  50K | `[800000:850000]`  |
| 100K | `[800000:900000]`  |
| 200K | `[800000:1000000]` |
| 400K | `[800000:1200000]` |

每个规模必须：

* 从同一个R12 frozen CP10 base创建独立fresh clone；
  -不得从前一个规模的更新结果继续；
  -保持输入为嵌套prefix；
  -使用相同instrumented binary和统计定义。

对每个component报告：

```text
total_write_bytes
write_bytes_per_replacement
write_calls
unique_4k_pages
page_rewrite_factor
fsync_count
```

可进行：

```text
total_write_bytes(N) ≈ fixed_cost + marginal_cost × N
```

但拟合只作为描述性分解。

若残差明显、成本非线性或per-replacement成本随N变化，不强行宣称固定成本加线性边际成本模型成立。

DGAI默认只执行100K reference。只有OdinANN结果需要进一步对照时，再扩展DGAI规模实验。

## 7. 结论限制

本轮不得提前声称：

* online visibility导致4.26倍写入；
  -邻居修复是主要写入来源；
  -WAL、save或consolidation是主要成本；
  -已经形成可投稿的新机制；
  -跨系统绝对性能差异具有严格因果性。

只有在定位到稳定、占比高、可修改且具有系统意义的写入来源后，才能进入novelty审查和机制设计。

## 8. 执行权限

Codex可以自行处理：

-实验目录创建；
-owner和mode；
-systemd unit命名；
-log/result落盘；
-不影响实验语义的脚本路径问题。

遇到以下情况必须停止：

-更新区间或数量错误；
-active-set、visibility或query失败；
-instrumentation改变索引结果；
-主要write path无法覆盖；
-frozen source或共享输入可能被修改；
-需要删除历史数据或修改其他磁盘。

## 9. 输出

源码审计与100K pilot统一输出：

```text
codex/share/2026-07-17/
dynamic_vamana_write_attribution_m0_0717.md
```

如100K pilot通过并完成多规模实验，可在同一报告中追加固定/边际成本分析。

完成后停止，等待机制与novelty评审。
