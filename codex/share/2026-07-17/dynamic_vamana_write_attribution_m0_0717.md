# Dynamic Vamana Write Attribution M0

## 研究目标与证据边界

本轮实验只定位 DGAI 与 OdinANN 的应用层持久写来源，回答更新期间哪些阶段、文件和页产生写请求，以及 OdinANN 的目标节点写入与邻居修复页写入各占多少。实验不设计新系统，也不把跨系统写入差异提前解释为 online visibility 的因果代价。两套系统的构建布局、I/O 引擎和可见性语义不同，因此绝对性能和绝对写量比较均保持描述性。

> **Application-requested write bytes**
> 应用通过 POSIX、Linux AIO 或 io_uring 提交的写入长度之和。该指标表示软件请求量，不等于设备最终执行量；后者通过独立 cgroup NVMe 计数记录。

> **Logical RMW role**
> 插入代码在提交写请求前已经形成的 4 KiB 页级 RMW(Read-Modify-Write，读改写)集合。M0 只读取该集合并按目标节点、邻居修复和二者共页分类，不改变页集合、写入顺序或并发执行。

## 源码调用链审计

### DGAI 更新路径

DGAI 的入口位于 `tests/w1_canary.cpp`。`run()` 构造 `pipeann::DynamicSSDIndex`，随后把私有 clone 的 `index_disk.index` 重新以可写方式打开。更新调用链为 `run()` → `insertion_kernel()` → `DynamicSSDIndex::insert()` → `SSDIndex::insert_in_place()`。`insert_in_place()` 完成候选搜索与剪枝，形成新节点及被修复邻居所在页的 RMW 集合，再由 `LinuxAlignedFileReader::write()` 或 `send_io()` 走 libaio `io_submit()` 提交。

DGAI 的删除调用链为 `run()` → `deletion_kernel()` → `DynamicSSDIndex::lazy_delete()`。该路径更新内存中的删除集合。`v2::Journal::append()` 的持久化主体在当前实际源码中被注释，因而本构建没有可归因的 WAL(Write-Ahead Log，预写日志)写入。删除只有在 `merge_kernel()` → `DynamicSSDIndex::final_merge()` → `save_del_set()` → `SSDIndex::merge_deletes()` 阶段才进入持久化合并。

当前构建没有定义 `USE_TOPO_DISK`，因此更新热点是共置节点文件 `index_disk.index`，不能依据目录中遗留的 `disk_index_graph` 和 `disk_index_data` 文件推断本次更新正在分别写图和向量。`index_disk.index` 的节点记录同时包含向量与邻接信息，系统调用层统一记为 `graph_vector_combined`。`index_disk.index.tags`、映射文件和索引头记为 metadata，PQ(Product Quantization，乘积量化)文件记为 vector。

### DGAI delta 状态与查询可见性

DGAI ingest 后的状态由可写动态索引对象、页级原地更新、标签映射和内存删除集合共同组成。当前 `w1_canary` 明确在 `ingest_end` 后记录 `online_visibility_unsupported`，随后执行 `final_merge()`。当前 fresh query path 会在新进程中从已发布的磁盘 prefix 重新构造索引，无法读取前一更新进程私有的未发布内存状态，因此必须在 publish/reload 完成后验证 fresh visibility。该结论只适用于当前实验查询路径，不外推为 DGAI 所有可能 API 都无法进行进程内查询。

### OdinANN 更新路径

OdinANN 的入口同样位于 `tests/w1_canary.cpp`。`DynamicIndex::load(prefix, true)` 先把正式文件复制到 shadow prefix，再加载 shadow 版本；这部分 8 GiB 级复制属于 load，不进入更新窗口归因分母。插入调用链为 `run()` → `insertion_kernel()` → `DynamicIndex::insert()` → `do_insert()` → `SSDIndex::insert_in_place()`。

`SSDIndex::insert_in_place()` 先分配目标 ID 和位置，执行图搜索与剪枝，然后把目标节点和所有待修复邻居的位置合并为页级 RMW 集合。目标节点的坐标、邻接表以及邻居节点的完整记录均位于同一节点页布局。写请求经 `wbc_write()` 进入后台任务，最终由 `LinuxAlignedFileReader::write()` 通过 `io_uring_prep_write()` 和 `io_uring_submit()` 提交。源码内可以根据目标位置和邻居位置区分 RMW 页角色；系统调用层只能看到合并后的 `graph_vector_combined` 写入。

OdinANN 的删除调用链为 `run()` → `deletion_kernel()` → `DynamicIndex::lazy_delete()`。该函数更新 `deleted_nodes_set_`、`deleted_nodes_` 和内存索引 tombstone，不在 ingest 阶段直接写删除文件。publish 调用 `DynamicIndex::save()`，其主要路径为 `SSDIndex::merge_deletes()`、reload、double-version copy 和再次 reload；同时写入合并后的节点文件、tags 与相关 metadata。

### OdinANN online visibility 时点

OdinANN 同时启动 insertion 与 deletion future，在两个 future 返回后执行进程内 online probe，然后才调用 `DynamicIndex::save()`。因此 online visibility 建立在 tag-to-ID、ID-to-location、loc-to-ID、内存删除集合以及页缓存或已排队的页 RMW 可被当前对象一致读取之后，不依赖最终 save/publish。由于 `BG_IO_THREAD` 会把实际页写交给后台队列，future 返回不应被解释为所有设备写均已落盘；页锁、缓存引用和后台任务共同维护写入完成前的读写一致性。M0 会分别记录 online probe 前后的应用写与设备写，但不会把当前进程内可见性等同于崩溃持久性。

## 插桩设计

独立 instrumented binary 构建于项目 NVMe 的 `build/write-attribution-m0-v3`，不修改 canonical binary、R12 frozen CP10 clone 或历史结果。二进制保留原始 DGAI libaio 和 OdinANN liburing 配置，并显式加载 `libm0write.so`。profiler 在内存中聚合，进程退出时以 `O_EXCL` 方式只写一次 `app_write_profile.json`，不产生逐操作日志。

真实写总账覆盖 `write()`、`pwrite()`、`pwrite64()`、`writev()`、`pwritev()`、`io_submit()` 和 `io_uring_submit()`，并记录 `fsync()` 与 `fdatasync()`。每个写请求按 phase、component 和真实文件路径累计 requested bytes、调用次数、唯一 4 KiB 页、页触及次数、重复写页数、最大页写次数和 page rewrite factor。phase 包括 load、insert/neighbor repair、delete、metadata、visibility、publish/save 与 other；component 包括 graph、vector、graph/vector combined、delete/tombstone、metadata 与 other。

源码内部只增加 `m0_record_role_page()` 弱符号回调。回调遍历已经生成但尚未提交的 `writes_4k`，把页分为 `insert_target`、`neighbor_repair` 和 `insert_target_neighbor_shared_page`。三类 logical RMW bytes 的总和用于交叉检查真实 insert 写请求，但不替代系统调用总账，也不把共页字节强制拆给任一方。

## 实验矩阵与门禁

100K pilot 对 DGAI 和 OdinANN 分别从 R12 CP10 PASS freeze evidence 创建 fresh private clone，使用完全相同的 master trace `[800000:900000]`。每次运行验证 trace 数量、派生活跃集合、持久 tags、18 个 online/fresh visibility probe、fresh-process query smoke、R12 source content/mode 不变、instrumented binary 独立性、无 OOM 和正向 cgroup NVMe 写入。

application attribution coverage 的分母为 update window 中所有捕获的应用写字节，分子为能够同时落入明确 phase 和明确 component 的字节。`graph_vector_combined` 是由实际节点布局支持的明确 component，不作为 unknown。coverage 必须达到 90%，否则停止且不扩展。

只有 DGAI 与 OdinANN 100K 均 PASS 后，才复用 OdinANN 100K pilot，并新增 50K、200K 与 400K fresh clone，形成 `[800000:850000]`、`[800000:900000]`、`[800000:1000000]` 和 `[800000:1200000]` 的嵌套 prefix。每个规模均从同一 R12 CP10 base 独立开始，不从前一规模继续。

## 当前执行状态

源码审计、独立二进制构建、空输出格式验证和运行器静态实现已完成。首次执行 `pilot3_sift10m_write_attribution_m0/DGAI/m0-n100000-01` 已完整执行 100K 更新，但归因门禁按设计判定 FAIL。该次运行的 ingest、publish 和 end-to-end wall time 分别为 102.515、26.640 和 129.156 秒，active-set exact、fresh visibility/query smoke、R12 source preservation、OOM 与索引健康均通过，cgroup NVMe 读写分别为 65.912 GB 和 8.472 GB。

首次 FAIL 的原因是 profiler 环境错误地施加在 `w1_stage_io_primer.py` 与 `resource_probe.py` 外层。primer 启动的前置 `dd` 继承 `LD_PRELOAD`，先按 `O_EXCL` 创建了空 profile；真实 driver 随后不能覆盖该文件，最终 application attribution coverage 为 0。该问题不影响索引语义或设备计数，但 application profile 无效，因此 OdinANN 未启动且该点不进入结果分析。

最小修复把 `LD_PRELOAD`、`ATLAS_M0_INDEX_ROOT` 和 `ATLAS_M0_PROFILE_OUTPUT` 仅下沉到 resource probe 启动的 driver 子进程。R02 使用全新的 `pilot3_sift10m_write_attribution_m0_r02` 与 `m0-n*-02` clone/result，不复用或覆盖首次失败现场。正式结果将在 R02 machine summary 通过后追加 phase/component、logical RMW role 与固定/边际成本分解。

## R02 覆盖率阻塞

R02 的 DGAI 100K 更新已完成，trace 仍为 master `[800000:900000]`。active-set exact、fresh visibility/query smoke、R12 source content/mode preservation、instrumented binary 独立性、resource return code、OOM 与正向设备写入均通过；ingest、publish 和 end-to-end wall time分别为 89.172、26.171 和 115.343 秒，peak process-tree RSS 约 3.59 GiB，cgroup NVMe 读写分别为 65,911,279,616 和 8,471,224,320 bytes。

然而，R02 的 machine summary 所报 `coverage=1.0` 不可接受为 M0 写路径覆盖率。该分母只包含 profiler 已经捕获的 3,553,847,441 application-requested bytes，因此只证明“已捕获记录能够分类”，没有证明主要应用写路径均已进入账本。捕获量仅相当于设备写量的 41.95%；二者本来不要求字节相等，但 4,917,376,879 bytes 的巨大差额与源码已知 publish 主索引重写缺失同时出现，足以否决当前覆盖门禁。

已捕获的 insert 总账为 3,009,847,296 bytes、414,606 次 write request、608,401 个 unique 4 KiB pages，page rewrite factor 为 1.2078。源码内 logical RMW role 与该 insert 总账逐字节相等：

| logical RMW role | requested bytes | insert 占比 |
|---|---:|---:|
| insert target only | 790,528 | 0.03% |
| insert target + neighbor shared page | 408,809,472 | 13.58% |
| neighbor repair only | 2,600,247,296 | 86.39% |

这些比例只描述 DGAI 已覆盖的 insert RMW，不代表完整 end-to-end 写入归因，也不用于提前解释 DGAI/OdinANN 的系统差异。

publish 阶段仅捕获 544,000,088 bytes 和 3 次 write request。该字节数与约 512,000,008-byte PQ 文件、32,000,008-byte tags 文件及少量 metadata 相符，却因 fd-path cache 在 fd 复用后陈旧而全部误标为 `index_disk.index`。更重要的是，`SSDIndex::merge_deletes()` 通过 `LinuxAlignedFileReader::write_fd()` → `execute_io(..., is_write=true)` → libaio `io_submit()` 重写主 `index_disk.index`，但该主路径在 profile 中不存在。因此当前账本同时存在“主要 publish I/O 未捕获”和“已捕获 POSIX 输出路径误标”两类 instrumentation defect。

发现该缺口后，controller 已在启动 OdinANN driver 之前停止。OdinANN 只短暂进入 fresh-clone 准备并由清理逻辑移除，没有形成实验 attempt；50K/100K/200K/400K 扩展矩阵完全未启动。当前没有活动的 M0 tmux 或 transient systemd unit。R02 的 DGAI clone/result 完整保留为失败证据，machine `status=pass` 与 `coverage=1.0` 明确作废，不进入结果分析。

建议的 v4 最小修复是把 `LinuxAlignedFileReader::write()` 与 `write_fd()` 中已经形成的 `IORequest` 作为 AIO/io_uring 主路径的 authoritative internal ledger，同时把 POSIX 输出保留为独立 ledger；validator 按来源去重，不能再以“已捕获字节”为自己的完整性分母。profiler 每次记录通过 `fstat(dev, ino)` 校验 fd identity，避免 close interposition 未命中后 fd 复用导致路径陈旧；跨 4 KiB header/component 边界的请求按实际 offset 拆分。修复后必须重新构建独立 DGAI/OdinANN binary，重复 synthetic test，并从同一 CP10 base 创建新的 fresh clones；只有双系统 100K 的源码路径清单逐项覆盖且归因完整性门禁通过，才允许规模扩展。

本轮按 Write Attribution M0 裁决中的“主要写路径无法覆盖则停止并报告”执行，现等待 Gpt 审阅该阻塞与 v4 方案，不自行越过门禁重跑。

## V4 实现与 R03 启动门禁

Gpt 已确认 R02 停止有效，并授权使用 fresh R03 只重跑 DGAI 与 OdinANN 的 100K 点。V4 将 physical async request、POSIX output 和 logical role 分为三个互不相加的账本。DGAI 当前 libaio 构建与 OdinANN 当前 io_uring 构建的 insert 后台刷写和 publish 主索引重写均汇入各自 active backend 的 `execute_io(..., write=true)`；插桩只在异步层确认完整提交后逐个记录 `IORequest`，不再拦截 `io_submit()` 或 `io_uring_submit()`，从结构上避免 wrapper 与 submit 双计数。同步 `write()`、`pwrite()`、`pwrite64()`、`writev()` 和 `pwritev()` 进入独立 POSIX 账本。每次物理记录均实时执行 `fstat()` 并重新解析当前 FD 路径，不保留跨调用 FD path cache。

V4 profile 对每条记录保存 ledger、source entry、phase、component、device、inode、offset 派生页范围、bytes 和 request count。`index_disk.index` 的首个 4 KiB 根据格式记为 metadata，其余节点页根据本轮已审计的共置布局记为 `graph_vector_combined`；跨边界请求按实际字节区间拆分。logical role 仍只解释 insert RMW，不加入 physical application total。

完整性门禁不再使用 captured-only 分母。validator 固定审计 async、五类 POSIX API、sync API 与 logical role 的唯一 ledger 归属，并逐项输出本工作负载是否触发；async source entry 与 logical role 必须触发。physical total 必须与 bucket total、entry total 精确一致，private clone 更新前后内容 manifest 中每个发生变化的索引文件都必须存在对应物理记录。账本内部明确 phase/component 的字节覆盖率必须不低于 90%。device bytes 只作为正向 sanity check，不进入 application coverage 分母。

独立构建位于项目 NVMe 的 `build/write-attribution-m0-v4-r02`。首次 V4 build 在 synthetic harness 的 `-Werror=misleading-indentation` 处提前停止，仅产生约 100 KiB 半成品；修正后使用新目录构建，不复用失败现场。DGAI 与 OdinANN instrumented binary SHA-256 分别为 `d3b7fec8...420ac` 和 `3b6a6163...49c71`，均不同于 canonical binary；profiler SHA-256 为 `54544d74...8d74d`。

正式运行前的 empty、POSIX、跨 component 边界、FD close/reuse、libaio 与 io_uring synthetic tests 全部通过。受限交互进程不能创建 io_uring，因此该项在与正式实验相同的 root-created、`--uid ubuntu` systemd unit 中执行，精确记录 4,096 bytes、1 request、1 unique page；没有用模拟结果替代。跨边界测试把单个 4,096-byte request 精确拆为 2,048-byte metadata 与 2,048-byte `graph_vector_combined`，physical request count 仍为 1；FD reuse 测试记录到两个不同 inode 和正确文件名；empty workload 的三个账本均为空。

R03 固定使用 `pilot3_sift10m_write_attribution_m0_r03`、`DGAI/m0-n100000-03` 与 `OdinANN/m0-n100000-03`，从 R12 frozen CP10 source 创建 fresh private clone，只使用 master `[800000:900000]`。双系统均验证 active-set exact、visibility/query smoke、frozen source preservation、changed-file coverage、无 OOM 和 device-write sanity。双系统 100K 完成后 controller 写入 `scale_matrix_started=false` 并停止，不包含 50K/200K/400K 代码路径。

启动前项目 NVMe `/dev/nvme8n1` 可用 1,186,614,386,688 bytes，MemAvailable 为 257,154,740,224 bytes；R03 result/formal 路径均不存在，无 M0 transient unit 或 tmux。双系统 fresh clone 的可见空间预计约 28–32 GB，result 与日志低于 1 GB；按 R01/R02 DGAI 约 2 分钟及此前 OdinANN 更新数据，预计总 controller wall 为 8–20 分钟，保守上限 40 分钟。所有 build、clone、result 和临时文件均位于项目 NVMe，不使用系统盘。

R03 首次 controller 在任何 clone 或 driver 启动前因 `m0_run_one_v4.sh` 缺少 executable bit 退出。现场仅包含已经完整派生并设为只读的 100K input，约 33 MB；formal tree、DGAI/OdinANN result directory、systemd unit 和 mutable attempt 均不存在。修复把子脚本调用改为显式 `bash`，并新增 input-only continuation。continuation 必须同时验证 input manifest、formal tree 不存在、两系统 result 不存在、无 controller manifest 和无残留 unit，随后复用只读 input 并创建首次 fresh clone；首次 controller log 保留，不把该控制面停止伪装为未发生。
