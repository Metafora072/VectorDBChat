# Dynamic Vamana M0 R04：OdinANN-only Coverage Closure

## 裁决

接受 DGAI R03 100K 作为正式 M0 DGAI anchor。

OdinANN R03 保留为 terminal failure。其性能、物理写入量和 logical-role 比例均为 provisional evidence，不进入正式跨系统结论。

本轮只修复 `std::filesystem::copy(..., overwrite_existing)` 对应的真实复制入口，并使用 fresh clone 重跑 OdinANN 100K。不重跑 DGAI，不启动规模矩阵。

## 1. 先确认真实复制入口

在项目 NVMe 上创建小型 synthetic workload，使用与 OdinANN 相同的编译器、libstdc++ 和：

```cpp
std::filesystem::copy(
    source,
    destination,
    std::filesystem::copy_options::overwrite_existing
);
```

通过 syscall trace 确认真正成功返回的复制入口，例如：

* `copy_file_range`；
* `sendfile`；
* `read/write`；
* 其他实际观察到的入口。

不得根据常见实现直接猜测。

记录：

* 源文件和目标文件 device/inode；
* 调用入口；
* requested/returned bytes；
* 成功与错误返回；
* 目标内容与大小；
* FD关闭和复用后的身份正确性。

## 2. Profiler修复

只拦截 synthetic 实际确认的复制路径。

对于复制类调用：

* 以目标文件为physical write对象；
* 使用实时`fstat`绑定device/inode；
* 按成功返回的bytes记账；
  -失败或零返回不计入physical bytes；
  -记录目标offset或实际覆盖区间；
  -不得与现有write/pwrite或async ledger重复累计。

保留三套独立账本：

1. async physical ledger；
2. POSIX/copy physical ledger；
3. logical-role ledger。

新profiler必须是R03 profiler的严格超集。通过源码审计确认DGAI工作负载不会触发新增copy入口，因此DGAI R03无需重跑。

## 3. 自测

正式运行前验证：

* `std::filesystem::copy` synthetic能进入新增ledger；
  -目标device/inode正确；
  -returned bytes正确；
  -覆盖已有目标文件时统计正确；
  -FD复用不继承旧身份；
  -复制请求不会同时被copy与write ledger重复记录；
  -changed-file validator能覆盖复制后的tags文件；
  -普通DGAI synthetic不产生新增copy记录。

## 4. OdinANN R04

```text
run:
pilot3_sift10m_write_attribution_m0_r04

attempt:
OdinANN/m0-n100000-04
```

要求：

* 从R12 frozen CP10 OdinANN source创建fresh private clone；
  -复用已校验的100K只读input `[800000:900000]`；
  -不得复用R03 mutable clone；
  -验证active-set exact、online/fresh visibility、query smoke和source preservation；
  -记录async、POSIX/copy、logical-role、phase/component和device I/O。

必须覆盖六个变化文件，包括：

```text
index_shadow_disk.index.tags
```

所有写入口、ledger闭合、分类、changed-file coverage和正确性门禁均通过后，OdinANN R04才可接受。

## 5. Composed Closure

R04通过后生成M0双系统100K closure：

```text
DGAI R03 PASS
+
OdinANN R04 PASS
```

明确记录两套profiler版本，并证明R04新增hook不会被DGAI路径触发。

报告继续更新：

```text
codex/share/2026-07-17/
dynamic_vamana_write_attribution_m0_0717.md
```

本轮完成后停止，不自动运行50K/200K/400K矩阵，不开始系统设计。

若synthetic无法确认复制入口、出现重复计数、变化文件仍无记录或索引语义异常，则停止汇报。
