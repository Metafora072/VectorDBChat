# 真实数据获取状态

## 存储决策

`/dev/nvme8n1` 原挂载内容约 12 GiB，包含已有 synthetic 数据、索引和历史 run，具有复现价值，因此未删除旧挂载点。设备已额外挂载到 `/home/ubuntu/pz/VectorDB/data` 并验证可写；旧 `/mnt/vectordb_nvme8n1` 保留作路径兼容。新数据、索引与 run 均放 NVMe，不占用只剩约 39 GiB 的系统盘。当前挂载为本次运行时配置，未擅自修改 `/etc/fstab`。

## 已获取数据

数据来自 ANN-Benchmarks 公共 HDF5：

- SIFT：`sift-128-euclidean`，1,000,000 × 128，10,000 queries，top-100 ground truth；源文件约 501 MiB。
- GIST：`gist-960-euclidean`，1,000,000 × 960，1,000 queries，top-100 ground truth；源文件约 3.6 GiB。

两套数据均按相同动态插入口径转换为 900K base + 后续连续 100K insert suffix，同时保留 1M full、query 与 ground truth。转换使用 `scripts/prepare_ann_benchmark_dataset.py`，逐块写入，没有把全量 GIST 载入系统盘。

## 可复现路径

- SIFT manifest：`/home/ubuntu/pz/VectorDB/data/VectorDB/datasets/real/sift-128-euclidean/dataset_manifest.env`
- GIST manifest：`/home/ubuntu/pz/VectorDB/data/VectorDB/datasets/real/gist-960-euclidean/dataset_manifest.env`
- 原始下载：`/home/ubuntu/pz/VectorDB/data/VectorDB/downloads/real/`

源文件 SHA-256：

- SIFT：`dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984`
- GIST：`8e95831936bfdbfa0a56086942e2cf98cd703517c67f985914183eb4cdbf026a`

所有生成的 bin 均验证了文件头 `(npts, dim)` 与实际字节数完全一致。当前 NVMe 使用约 28 GiB、剩余约 1.7 TiB；两真实数据集、两个维度的正式数据门禁已经解除。
