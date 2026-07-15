# 三系统 SIFT10M Pilot：官方 U8BIN 数据源修订

**日期**：2026-07-14
**上游门禁**：`gpt/share/dynamic_vamana_three_system_p1_authorization_0714.md`
**当前状态**：P1 尚未启动
**裁决**：**PASS — 批准使用官方 BIGANN U8BIN 主源，完成轻量 source canary 后直接启动 P1**

---

# 1. 修订原因

原 P1 授权文字要求标准 BIGANN `.bvecs` 输入。

经核对，BIGANN billion-scale benchmark 的正式 competition artifact 使用：

```text
base.1B.u8bin
query.public.10K.u8bin
```

其逻辑数据仍然是：

```text
BIGANN / SIFT
128 dimensions
uint8 vectors
squared L2 / Euclidean
```

因此，从官方 `u8bin` 主源提取前 10M vectors 与从原始 `bigann_base.bvecs` 提取前 10M vectors，在逻辑数据内容上属于同一标准数据集来源。

本次只修订输入容器格式，不改变：

* 数据点；
  -向量值；
  -向量顺序；
  -query set；
  -distance metric；
  -80/20 active/insert 划分；
  -replace-new trace；
  -GT 计算方法。

---

# 2. 正式批准的数据获取方式

## 2.1 Base corpus

从官方：

```text
base.1B.u8bin
```

取得文件前缀：

```text
8 + 10,000,000 × 128 × 1
= 1,280,000,008 bytes
```

其中：

* 前 4 bytes：原始 `n = 1,000,000,000`；
* 后 4 bytes：`d = 128`；
* 随后是前 10,000,000 个 uint8 vectors。

下载完成后生成规范化的：

```text
base.10M.u8bin
```

并将头部修改为：

```text
n = 10,000,000
d = 128
```

vector payload 必须逐字节保持不变。

## 2.2 Query corpus

下载完整：

```text
query.public.10K.u8bin
```

必须验证：

```text
n = 10,000
d = 128
file_size = 8 + 10,000 × 128
          = 1,280,008 bytes
```

---

# 3. Prefix 下载的正确性要求

可以优先使用 HTTP Range，但不能只假设服务器正确响应。

## Range 模式

请求：

```text
bytes=0-1280000007
```

必须验证：

* HTTP status 为 `206 Partial Content`；
* `Content-Range` 起点为 0；
  -终点为 1,280,000,007；
  -本地文件大小恰好为 1,280,000,008 bytes。

如果服务器返回 `200 OK` 并忽略 Range，脚本不能把响应静默当作正确 prefix。

## Streaming-prefix fallback

若服务器不支持 Range，可以采用与官方 benchmark loader 等价的方式：

-从文件起点开始流式读取；
-写满 1,280,000,008 bytes 后主动关闭连接；
-验证最终字节数；
-记录 `download_mode=streamed-prefix`。

不得为了这一实验下载并永久保存完整 128 GB 的 1B corpus，除非 prefix 获取确实无法工作并重新获得授权。

---

# 4. Header 与 payload 审计

下载的原始 prefix 必须先验证：

```text
raw header:
n = 1,000,000,000
d = 128
```

随后生成规范化 crop：

```text
normalized header:
n = 10,000,000
d = 128
```

并验证：

```text
raw_prefix[8:] == normalized_crop[8:]
```

建议以流式 SHA256 验证 payload，而不是将 1.28 GB 一次性读入内存。

provenance 同时记录：

```text
raw_prefix_sha256
raw_prefix_payload_sha256
normalized_u8bin_sha256
normalized_payload_sha256
```

其中两个 payload hash 必须一致。

---

# 5. Float32 canonical 转换

三套系统当前统一使用 float32 输入，因此将规范化的 uint8 corpus 转换为 float32：

```text
uint8 value x
→ float32 value float(x)
```

不得进行：

-归一化；
-中心化；
-缩放；
-PCA；
-重新排序；
-量化；
-随机采样。

转换后必须验证：

```text
n = 10,000,000
d = 128
dtype = float32
```

query 同样执行数值保持的 uint8→float32 转换。

provenance 记录：

```text
base_10m_u8bin_sha256
query_10k_u8bin_sha256
base_10m_fbin_sha256
query_10k_fbin_sha256
conversion_tool_sha256
conversion_command
```

---

# 6. Source identity

manifest 中记录：

```text
dataset = BIGANN
source_format = official-competition-u8bin
source_corpus = base.1B.u8bin prefix
source_query = query.public.10K.u8bin
source_review_status = official-benchmark-source
metric = squared-l2
dimension = 128
dtype_source = uint8
dtype_canonical = float32
```

不再标记为一般性的：

```text
operator-reviewed-standard-BIGANN
```

前提是 URL 与文件名确实来自官方 benchmark manifest 中登记的来源。

若改用其他镜像，则重新降级为：

```text
operator-reviewed mirror
```

并单独记录镜像身份。

---

# 7. Ground truth 边界

官方 BIGANN 可能提供完整 first-10M corpus 的 GT，但本实验 checkpoint 0 只包含 8M active vectors。

因此不能直接使用官方 full-10M GT。

仍按原门禁执行：

```text
8M checkpoint-0 active vectors
+ official 10K queries
→ exact top-100 GT
```

并完成独立 GT audit。

---

# 8. 脚本修订要求

`prepare_sift10m.sh` 改为同时支持：

```text
SIFT10M_SOURCE_FORMAT=u8bin
```

以及原来的：

```text
SIFT10M_SOURCE_FORMAT=bvecs
```

本次正式运行使用 `u8bin`。

新增或修改：

```text
download_u8bin_prefix.py
convert_u8bin_to_fbin.py
sift10m_provenance.py
prepare_sift10m.sh
```

必须完成：

* header 检查；
* prefix 长度检查；
* Range/stream mode 记录；
* header rewrite；
  -payload hash equality；
  -u8bin→fbin 转换；
  -canonical hash；
  -已有文件复用时重新核对 provenance。

---

# 9. tmux 环境变量传递

当前 P1 launcher 不能依赖 tmux server 继承调用 shell 中可能过期的环境变量。

`start_p1_tmux.sh` 必须显式传入：

```text
SIFT10M_SOURCE_FORMAT
SIFT10M_BASE_URL
SIFT10M_QUERY_URL
SIFT10M_BASE_EXPECTED_SHA256
SIFT10M_QUERY_EXPECTED_SHA256
ATLAS_ROOT
ATLAS_CHAT_ROOT
F0_ATTEMPT
ATLAS_NOTIFY_EMAIL
```

不允许只在启动 shell 中 `export` 后假设 tmux 能看到。

启动日志中对 URL 可以完整记录，但不得输出任何鉴权 token 或 secret query 参数。

---

# 10. 邮件预计时间

邮件继续包含：

* `phase`；
* `estimated_remaining`；
* `expected_finish_utc`。

另外增加：

```text
expected_finish_shanghai
```

以 `Asia/Shanghai` 时间展示，避免用户手动换算 UTC。

预计时间仍然是宽松窗口，不能伪装为精确完成承诺。

---

# 11. Source canary

不需要再发起一轮完整脚本审查。

Codex 完成格式支持后，先运行一个轻量 canary：

1. 读取官方 base 文件前 264 bytes；
   2.验证原始 header 为 `(1B,128)`；
   3.提取前 2 vectors；
   4.生成 `(2,128)` 的 normalized u8bin；
   5.转换为 float32；
   6.逐元素验证 float 值等于原 uint8；
   7.验证 payload hash 逻辑；
   8.验证 Range 响应或 streaming fallback；
   9.执行 `bash -n` 与 Python compile。

canary 通过后即可直接启动正式 P1，无需再次等待 Gpt 确认。

canary 失败则停止，不下载 10M prefix。

---

# 12. P1 执行授权

完成上述脚本修订和 source canary 后，继续原批准顺序：

```text
runtime canary
→ SIFT10M official u8bin prefix preparation
→ checkpoint-0 exact GT
→ DiskANN F0
→ DGAI F0
→ OdinANN F0
→ 汇总并停止
```

三系统 F0 完成后仍不得自动启动：

* slim W0；
* churn；
* DEEP/GIST；
* W2；
* Idea 提取。

---

# 13. 最终裁决

官方 `u8bin` 是比寻找非官方 `.bvecs` 镜像更合适的数据来源。

本次 source amendment 不改变数据集语义，只是采用官方 benchmark 的原生容器，并按照官方 10M crop 逻辑提取前缀、修正 header、转换成系统统一的 float32 canonical corpus。

**批准实施。**
