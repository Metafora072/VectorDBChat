# NVMe 历史 ANNS 索引清理记录（2026-07-24）

## 结论

已删除 232 个已结束实验的历史 `index` 目录，以及
`dynamic_vamana_atlas/tmp` 旧临时目录。文件系统实际释放
742,968,115,200 字节（691.943 GiB）。

`/dev/nvme8n1` 的占用由 1,087,592,931,328 字节（约 1,012.9 GiB）
下降到 344,624,816,128 字节（约 321.0 GiB），可用空间由约
727 GiB 上升到约 1.4 TiB，使用率为 19%。

## 删除范围

只删除以下四棵历史实验树中 basename 严格等于 `index` 的目录：

1. `dynamic_vamana_atlas/formal`
2. `dynamic_vamana_atlas/z0b_sequence_endpoint_reclaim_0719/work`
3. `runs/insert_cost_scale_substage/formal`
4. `recovered_system_disk_20260711/runs/insert_cost_closure`

另删除唯一指定的旧临时目录：

```text
/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/tmp
```

删除前门禁确认目标数量为 232。一次性对完整目标集合执行 `du`、对跨目录
硬链接去重后，索引目标占用为 746,728,136,704 字节。逐目录独立统计会把
共享 inode 重复计算，因此清单中的 `standalone_allocated_bytes` 不可直接
求和作为实际可释放空间；最终释放量以删除前后的文件系统 `df` 差值为准。

## 保留与复核

以下内容未删除，并在清理后完成存在性和容量复核：

```text
datasets   66G
index      68G
results   1.1G
build      17G
```

同时保留仓库中的脚本、manifest、实验日志、压缩结果和报告。清理后以 root
权限完整遍历四棵目标树，残余 `index` 目录数为 0；旧 `tmp` 目录不存在。

## 可恢复性

被删除内容不是仓库资产，不能通过 Git 恢复；若后续确有需要，只能从保留的
数据集、配置、脚本和构建产物重新构建索引。删除前完整目标清单保存在：

```text
codex/work/2026-07-24/nvme_cleanup_0724/index_dirs_before.tsv
```

执行脚本包含挂载设备、精确根目录、目录类型、数量和去重实占字节门禁，便于
审计本次清理范围，但不应在目标已经删除后重复执行。
