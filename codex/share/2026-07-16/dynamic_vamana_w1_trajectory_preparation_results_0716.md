# Dynamic Vamana W1 Trajectory Preparation Results

## 结论

CP05、CP10、CP20 的单一 master-trace 前缀、active sets、active vectors、visibility probes 与 location-ID exact GT preparation 全部通过。该轮仅准备冻结输入，没有创建动态索引 clone，没有运行 DGAI/OdinANN update、checkpoint query、DiskANN stale control 或 rebuild。

## Master trace 与 CP01 前缀

- master records：`1,600,000`；binary SHA256：`039fdff996d26dc51ca3715f2a9b3b32a840feb6fb6aa49e3d3be838df357880`。
- master TSV SHA256：`925686659fd0db94e87bb25e4632bbb511e6a36dea6643ecc7db4a5390dd980d`；manifest SHA256：`90aec8b89699a044d422e8761fb827a87f8e7a2d0b01833c68db7d50ba03d772`。
- CP01 80K logical record payload：逐条 exact；证据 SHA256：`60bd33e0d5ecc4834588c9ce09d8e5ce0dde97fe43185be282621baad98d775e`。
- CP05/CP10/CP20 分别是 master 的前 400K/800K/1.6M records；delete 与 insert sets 严格嵌套。

## Checkpoint artifacts 与 GT

| Checkpoint | Replacements | Active tags | Trace bin / TSV SHA256 | Active tags SHA256 | Active vectors SHA256 | Probe spec / vectors SHA256 | Final GT SHA256 | GT validation SHA256 | Tag 0 |
|---|---:|---:|---|---|---|---|---|---|---|
| CP05 | 400000 | 8000000 | `e7cd1140fd78a170ad5269f655741706f0caf5a25cbe8909af87bb0abbfa34ae` / `f27f95bbf960ca76d5f0bc1b921a21a7385b2a7369d77d4cbdef3abc23015a44` | `a0644c853207f9525615428abd7056ce5526ece9f24e0ccddaf5f8be3ca88194` | `44bd903d798b179a469f58464ff180ea09f5b4b930293393a67d6f236ad742dc` | `190f0c8d46dfa86e75bc46ad3b08d6296ed3ea3599224b967d68483f3b44268e` / `143034dbfa6e7f233547d7d5ca44855b2eb03f0dadd162f57d998d62fead8cf3` | `efd6c8e5b03059d9dc025621a0c4a98c36756cbdb64ed15ab9c4b305ff27cffe` | `2813df3f6ae533e74cdd857567edb86daa972f28523211f055f21e0b1bdfb6c3` | active |
| CP10 | 800000 | 8000000 | `4217f3769b89dfbea2177f876d7dab7b2c86185420d664525e2fb242d4de27ea` / `528b9211c5df172ec321cfa9433b2a0d22e3e149cbb788ba1da169c6e7ff6e8f` | `9c6743159ab311eb278c271875e9cf6ef9808b40afe734e77ffa2551933571a7` | `2fb29c64d7ee1e71445a3f0de2789576f572353e1e1d388f639d05e225ae9283` | `348ab9afa7078bab962a47a61a466efeef822107c34018341800dcaf3cd15669` / `ca7b56eb453459f46145e87ebfa191b729bb83e1ae34f5a394f68b08681cb6d8` | `ffbe8b9392aa391012a4fddfeb714cb54777d79fcf9e560f6928aa915c77cf69` | `226ee5d4201787ca3d788bb1d01ebba3d6783a53985ba333633211739251d869` | active |
| CP20 | 1600000 | 8000000 | `039fdff996d26dc51ca3715f2a9b3b32a840feb6fb6aa49e3d3be838df357880` / `925686659fd0db94e87bb25e4632bbb511e6a36dea6643ecc7db4a5390dd980d` | `ab9739b4ad862217f0d4f29ea6966450920cd60bda9943991665b3e7cacee197` | `25342b4da98139f3e8d242555224dad6ad87ae5eede3a1e357caeb385de5570c` | `9e403a6a28754fa6c16cee2e0362fb800d8dd7ea036854a4b8a37994cff91b69` / `e78abc7f7bad7179fac2bd6b1ba42e7e534ad5d0b36b915b461d32053fa78ed0` | `2420b8c51d103dfdd4763cd41ef4e340650860ec1020f6758c16d0825bb503a4` | `ada7ab5625b611fe4d2505df94313db9b2dbe804f867d54fb4699999f0795ae6` | active |

每个 GT 均为 `10000×100`，location IDs range/uniqueness、final active tags、deleted absence、row uniqueness、finite/monotonic distances、remap distance block byte identity 和 less-than-K warning absence 全部通过。每个 checkpoint 均完成固定 36-query brute-force audit：保存 raw 正式/独立列表与逐项比较，并按 `(recomputed squared-L2 distance, tag)` canonicalize 后逐位置 exact；raw 顺序差异只允许来自等距组，distance 逐位置容差为 `5e-3`。

### 36-query 独立审计身份

| Checkpoint | Query IDs | Audit count | GT manifest SHA256 | Location GT SHA256 | Compute log SHA256 |
|---|---|---:|---|---|---|
| CP05 | `0,17,7150,9999,3582,2111,5996,9829,9308,4356,3548,8479,3072,1819,4141,9576,3757,4782,9848,2741,5387,6771,9972,6644,1971,47,6348,8122,7913,1862,7103,7767,7546,8514,6477,5677` | 36 | `10467693059967a66cac937b28bd08edeee73db77652c9a5e59ea1a3a008f0ac` | `e25185db2272104e8b1487f16292c0a08bd7faaee90cd13bdf7d968d02c2c18a` | `4771da6a5077a5451ff5680636611ec6001d9b141e688d7a8d1a00e66cd527ae` |
| CP10 | `0,17,7150,9999,3582,2111,5996,9829,9308,4356,3548,8479,3072,1819,4141,9576,3757,4782,9848,2741,5387,6771,9972,6644,1971,47,6348,8122,7913,1862,7103,7767,7546,8514,6477,5677` | 36 | `05099744c248a6e476b4f5891f0f21dda1962d1d0cb7288555d54286f3449094` | `b805cb949ec673499e640c4af9fac567ab48168c24bf01dd5840d4af2ec0ea16` | `7e95019517ddb644ae90d840485f2654b938d59a5be84f218c9233554d20d780` |
| CP20 | `0,17,7150,9999,3582,2111,5996,9829,9308,4356,3548,8479,3072,1819,4141,9576,3757,4782,9848,2741,5387,6771,9972,6644,1971,47,6348,8122,7913,1862,7103,7767,7546,8514,6477,5677` | 36 | `ca5890a52eed47ab506b9853d8478eb4f37b5b9f802857b4a6ff4e0112ac6dfb` | `476a6896bac16e01e14154a142311f194b0b828ad72f4d4419cae5e533418953` | `e0b13331aa1d63635d8f95c279b26378142357ebfde420f782d266230b2e0d11` |

## 资源

| Stage | Wall(s) | Peak RSS(B) | cgroup peak(B) | NVMe R/W(B) | Output apparent/allocated delta(B) |
|---|---:|---:|---:|---|---|
| master_trace | 2.638 | 210841600 | 231415808 | 0/62681088 | 62668645/62681088 |
| cp05_derive | 1.219 | 150851584 | 155566080 | 4096/47448064 | 47436787/47448064 |
| cp05_materialize | 9.574 | 9300258816 | 4279717888 | 4096/4096024576 | 4096011300/4096028672 |
| cp05_gt | 83.353 | 20605321216 | 20665323520 | 0/16719872 | 16678933/16691200 |
| cp10_derive | 1.523 | 113463296 | 171884544 | 0/62992384 | 62981292/62992384 |
| cp10_materialize | 8.963 | 9299759104 | 4281749504 | 0/4096024576 | 4096011303/4096028672 |
| cp10_gt | 81.551 | 20600901632 | 20664475648 | 0/16719872 | 16679048/16691200 |
| cp20_derive | 2.029 | 118685696 | 204017664 | 0/94683136 | 94670061/94683136 |
| cp20_materialize | 8.853 | 9299517440 | 4279697408 | 0/4096024576 | 4096011309/4096028672 |
| cp20_gt | 81.607 | 20601393152 | 20664852480 | 0/16719872 | 16679199/16691200 |

Trajectory dataset tree apparent/allocated：`12555790697/12555890688 B`；GT tree apparent/allocated：`50037180/50073600 B`。项目 NVMe final free：`1327459942400 B`。

十个 preparation stage 均使用独立 scope；每份资源证据强制绑定 command、scope、space root、项目 NVMe `259:10` 的 baseline/final I/O、完整 space samples 与无 OOM memory.events。资源 JSON 的 SHA256 已收录于 trajectory validation。

## Cross-checkpoint invariants 与边界

Master/checkpoint prefix、历史 CP01、三组 8M cardinality、delete/insert nesting、active-set difference、全量 vector row/tag mapping、完整 probe semantics、GT active-only、GT source/tool identity、read-only inode-disjoint artifacts 与全部 output hashes 均已冻结。

- trajectory validation SHA256：`cb19e056eb19fbdac27a6d52b98757427c981f9f5d78dd710ad7246c3c4f7848`。
- final CP01/formal-input preservation：`pass`；SHA256：`6405551d62fa6f42ee245880b684e0ca1b4eb69a6651d9964289ada2b85413e1`。
- 后续 cumulative trajectory update 必须另行审议；本轮停止，不进入动态执行。
