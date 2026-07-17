# Dynamic Vamana Write Attribution M0：V4 修复门禁

## 裁决

M0 R02 停止有效。

R02 的 DGAI 100K 更新正确性与资源数据可以保留，但 application write attribution 作废，不进入正式归因分析。

授权修复 instrumentation，并使用 fresh R03 重跑双系统 100K。暂不运行 50K/200K/400K 矩阵。

## 当前有效线索

在已经捕获的 DGAI insert RMW 中：

* target only：0.03%；
* target + neighbor shared page：13.58%；
* neighbor repair only：86.39%。

该比例只描述当前已捕获的 insert ledger，不代表完整 ingest、publish 或 end-to-end 写入。

## V4 统计结构

使用三个相互分离的账本。

### 1. Physical async-request ledger

记录真正提交给异步 I/O 层的每个写请求。

DGAI 应在最终公共 AIO 提交位置记录，例如形成完整 `IORequest` 并进入 `execute_io(..., is_write=true)` 的位置。

OdinANN 应根据源码定位最终 io_uring SQE 构造或提交位置。

每个请求只能记录一次。不要同时在 `write()`、`write_fd()` 和底层 submit 中重复累计。

至少记录：

* phase；
* component；
* device/inode；
* offset；
* length；
* request count；
  -4KiB page范围。

### 2. POSIX-output ledger

单独记录不经过上述异步提交层的：

* write；
  -pwrite；
  -writev/pwritev；
  -文件流输出；
  -其他实际存在的同步输出路径。

通过 `fstat(fd)` 获取实时 device/inode。不得仅依赖可能因FD复用而陈旧的path cache。

需要路径时，从当前FD身份重新解析或验证。

### 3. Logical-role ledger

保留高层语义分类：

* insert target；
  -neighbor repair；
  -delete；
  -metadata；
  -other。

该账本只用于解释异步物理写请求的逻辑来源，不再次加入application total，避免重复计数。

## Component 分类

优先按真实文件身份分类。

对于一个文件内部包含多个区域的情况，根据实际布局和offset划分；跨边界请求按实际字节区间拆分。

无法由源码或格式可靠确定的区域标为`unknown/index-body`，不得强行标记为graph、vector或metadata。

## 完整性定义

不再使用：

```text
classified captured bytes / all captured bytes
```

作为写路径完整性。

新的完整性门禁包括：

1. 源码审计列出的每个写入口都被分配给唯一账本；
2. 每个写入口明确标记为“本次执行已触发”或“本工作负载未触发”；
3. 不允许一个物理请求被多个账本重复累计；
4. 所有发生内容或大小变化的索引文件都有对应写记录；
5. ledger内部至少90%的bytes能归入明确phase和component；
6. device write只作为独立sanity check，不作为application coverage分母。

Application bytes与device bytes不要求相等，因为可能存在对齐、文件系统、缓存和设备层放大。

## 修复测试

正式运行前至少验证：

* DGAI AIO synthetic write能够进入async ledger；
  -OdinANN io_uring synthetic write能够进入async ledger；
  -POSIX write能够进入POSIX ledger；
  -FD关闭并复用后不会沿用旧文件身份；
  -一个异步请求不会在wrapper和submit层重复计数；
  -跨component边界的请求能够正确拆分；
  -空工作负载不会生成虚假写入。

## R03 运行

```text
run:
pilot3_sift10m_write_attribution_m0_r03

attempts:
DGAI/m0-n100000-03
OdinANN/m0-n100000-03
```

两个系统均：

* 从R12 frozen CP10 source创建fresh private clone；
  -使用master `[800000:900000]`；
  -执行100K replacements；
  -验证active-set exact、visibility、query smoke和source preservation；
  -记录ingest、publish、end-to-end的application与device I/O。

R01/R02 result保留为失败证据，不复用其mutable clone。

## 本轮停止点

双系统100K通过后停止并提交审议，不自动启动50K/200K/400K矩阵。

报告必须分别给出：

* async physical writes；
  -POSIX outputs；
  -logical roles；
  -phase/component分解；
  -unique 4KiB pages；
  -page rewrite factor；
  -device I/O；
  -仍未覆盖或无法解释的路径。

只有双系统100K归因完整后，再决定是否进行规模分解。

## 输出

继续更新：

```text
codex/share/2026-07-17/
dynamic_vamana_write_attribution_m0_0717.md
```

普通权限、目录、owner和unit命名问题可自行最小修复。写入口遗漏、重复计数、索引结果变化或共享数据风险必须停止。
