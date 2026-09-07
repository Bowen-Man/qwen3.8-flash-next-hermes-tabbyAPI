# Benchmark 与本地测试指南

[English](benchmark.md) | **简体中文**

这一页有两个目的：

1. 展示本仓库在参考机器上的实测性能；
2. 告诉你怎样在**自己的本地模型和硬件**上复现同样的测试。

这套测试面向本地长上下文 Agent，重点关注：

- 首次请求 TTFT；
- 长 prompt ingestion / prefill 性能；
- decode throughput；
- 完全相同 prefix 的 cache reuse；
- TabbyAPI 系统内存 recurrent/KV cache 配置的影响。

> 当前仓库中的大多数 cache 组合是单次工程测试。如果要严谨比较，建议每个配置至少重复 3 次并报告中位数。

---

## 1. 我们到底在测什么？

benchmark 脚本：

```text
scripts/benchmark_chat.py
```

使用：

```text
--cache-reuse
```

时，同一段长 prompt 会连续发送两次：

```text
Run 1
└─ 带随机 nonce 的长 prompt
   └─ 首次处理

Run 2
└─ 完全相同的 prompt
   └─ repeated-prefix / cache-reuse
```

脚本会先利用 server 返回的 token usage 进行 calibration，再构造接近目标长度的合成长 prompt。

不同次 benchmark invocation 会使用新的随机 nonce，避免上一轮长 prefix 被意外复用。

---

## 2. 各指标是什么意思？

### First-pass TTFT

从请求发出到收到第一个生成 token 的时间。

对于 32K、64K 长 prompt，它主要反映：

```text
prompt ingestion / prefill
+
调度与首 token 开销
```

越低越好。

### Approx. first-pass prompt rate

脚本按：

```text
actual_prompt_tokens / first_pass_TTFT
```

计算。

例如：

```text
64,000 tokens / 65 s ≈ 985 tok/s
```

对于首次请求，它可以作为一个实用的 long-prompt ingestion 指标。

但这不是纯 GPU kernel 层面的 prefill benchmark，因为 TTFT 还包含 HTTP、模板、调度和首 token 开销。

### Decode throughput

首 token 之后持续生成的速度：

```text
tokens/s
```

我们的 RTX 5070 测试中，即使 context 达到 64K，decode 依然约：

```text
20–21 tok/s
```

### Cached-prefix TTFT

第二次请求发送**完全相同的 prompt**。

如果 backend 能复用之前的 prefix state，TTFT 可以从几十秒下降到约 1 秒甚至更低。

这对 Agent 很重要，因为多轮 Agent 往往重复携带大量：

```text
system prompt
tool schema
conversation history
fixed prefix
```

### Cached run 的“几万 tok/s”不是真实 prefill

第二次请求可能出现：

```text
60K tok/s
100K tok/s
```

这不意味着模型真的每秒重新计算了十万 token。

大部分 prefix 已经被 cache 复用。

因此 cached run 的：

```text
prompt_tokens / TTFT
```

更应该理解成：

> effective cached-prefix reuse rate

而不是物理 prefill throughput。

---

# 3. 测试需要什么？

需要：

- 一个正在运行的 OpenAI-compatible 本地 endpoint；
- Python；
- `openai` Python package；
- `scripts/benchmark_chat.py`。

本仓库默认：

```text
Base URL: http://127.0.0.1:8088/v1
Model:    Qwen3.8-Flash-Next-exl3-3.05bpw
```

---

# 4. 最简单的跑法

## Windows + Hermes Python

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py"
```

## 32K

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 32000
```

## 32K + cache reuse

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 32000 `
  --cache-reuse
```

## 64K + cache reuse

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 64000 `
  --cache-reuse
```

## 普通 Python 环境

```bash
pip install openai
python scripts/benchmark_chat.py --prompt-tokens 32000 --cache-reuse
```

---

# 5. 测你自己的本地模型

指定：

```text
--base-url
--model
```

即可指向其他 OpenAI-compatible endpoint：

```powershell
python .\scripts\benchmark_chat.py `
  --base-url "http://127.0.0.1:1234/v1" `
  --model "your-local-model-id" `
  --prompt-tokens 32000 `
  --cache-reuse
```

可用于：

```text
TabbyAPI
LM Studio
vLLM
llama.cpp server
以及其他 OpenAI-compatible backend
```

前提是 backend 能在 calibration 请求中返回 token usage。

---

# 6. 第一次测试自己的模型怎么跑？

不要直接上 64K。

建议：

```text
短 prompt
→ 8K
→ 16K
→ 32K
→ 64K
```

每一步观察：

```text
请求能否完成？
VRAM 是否稳定？
RAM 是否异常增长？
TTFT 是否大致随 context 增长？
decode throughput 是否明显下降？
```

确认正常以后，再加：

```text
--cache-reuse
```

测试 repeated-prefix。

---

# 7. 怎么调 sysmem cache？

例如：

```yaml
memory:
  sysmem_recurrent_cache: 8192
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: false
```

最重要的原则：

> **一次只改一个变量。**

不要比较：

```text
4R / 4K
→
8R / 8K
```

然后把变化归因给某一个 cache。

更合理的是做一个小矩阵：

```text
Recurrent:
4 GB
8 GB
12 GB

KV:
4 GB
8 GB
```

例如：

```text
4R / 4K
8R / 4K
12R / 4K
4R / 8K
8R / 8K
```

每改一次：

```text
1. 停止 TabbyAPI
2. 修改 config.yml
3. 重启 TabbyAPI
4. 运行 benchmark
5. 保存结果
```

调 cache 时尽量保持这些设置不变：

```text
cache_mode
chunk_size
max_seq_len
CPU offload
CUDA allocator
```

---

# 8. 怎样让 benchmark 更可信？

亚秒级 cached-prefix TTFT 很容易受运行状态影响：

- Windows scheduler；
- allocator 状态；
- CPU/RAM 压力；
- cache residency；
- 后台应用；
- SSD activity；
- 上一轮 inference state。

正式比较时建议：

```text
同一个配置 ≥3 次
```

然后报告：

```text
median TTFT
range 或 IQR
```

而不是只挑最快的一次。

我们的实验也显示：

> first-pass TTFT 通常比 cached-prefix TTFT 稳定得多。

---

# 9. 参考硬件

```text
OS:             Microsoft Windows 11 教育版，64 位
OS version:     10.0.26200
CPU:            AMD Ryzen 9 9950X3D
GPU:            NVIDIA GeForce RTX 5070
VRAM:           12,227 MiB
System RAM:     93.6 GB
NVIDIA driver:  591.86

Python:         3.12.13
Torch:          2.9.0+cu128
CUDA runtime:   12.8
Model:          Qwen3.8-Flash-Next-exl3-3.05bpw
Backend:        ExLlamaV3 + TabbyAPI
```

主要配置：

```yaml
model:
  max_seq_len: 81920
  cache_size: 81920
  cache_mode: FP16

  cpu_moe_offload_layers: 999
  ngram_ram: false

  chunk_size: 2048
  output_chunking: true
  max_batch_size: 1

memory:
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: false
```

---

# 10. 本机实测结果

## 32K

| Recurrent | KV | First-pass TTFT | Cached-prefix TTFT | First-pass rate |
|---:|---:|---:|---:|---:|
| 4 GB | 4 GB | 33.539 s | 0.899 s | ~955 tok/s |
| 4 GB | 8 GB | 33.344 s | 1.340 s | ~959 tok/s |
| **8 GB** | **4 GB** | **32.773 s** | **0.531 s** | **~977 tok/s** |
| 8 GB | 8 GB | 35.288 s | 0.765 s | ~908 tok/s |
| 12 GB | 4 GB | 33.301 s | 1.396 s | ~961 tok/s |
| 12 GB | 12 GB | 33.403 s | 1.390 s | ~957 tok/s |

总体：

```text
First-pass TTFT:
~32.8–35.3 s

Long-prompt ingestion:
~0.91–0.98K tok/s

Decode:
~20–21 tok/s
```

32K 单次观测最快 cached-prefix：

```text
8R / 4K
0.531 s
```

---

## 64K

| Recurrent | KV | First-pass TTFT | Cached-prefix TTFT | First-pass rate |
|---:|---:|---:|---:|---:|
| 4 GB | 4 GB | 70.255 s | 1.813 s | ~910 tok/s |
| 4 GB | 8 GB | 65.403 s | 0.660 s | ~979 tok/s |
| **8 GB** | **4 GB** | **65.057 s** | **0.962 s** | **~985 tok/s** |
| 8 GB | 8 GB | 70.215 s | 1.029 s | ~912 tok/s |
| 10 GB | 4 GB | 65.692 / 65.185 s | 1.155 / 0.919 s | ~979 tok/s |
| 12 GB | 4 GB | 66.491 s | **0.539 s** | ~963 tok/s |
| 12 GB | 12 GB | 65.103 s | 1.062 s | ~984 tok/s |

`10R / 4K` 重复了两次：

```text
First-pass TTFT:
65.692 s
65.185 s

Cached-prefix TTFT:
1.155 s
0.919 s

平均 first-pass TTFT:
~65.44 s

平均 cached-prefix TTFT:
~1.04 s
```

总体：

```text
First-pass TTFT:
~65–70 s

Long-prompt ingestion:
~0.91–0.98K tok/s

Decode:
~20–21 tok/s
```

64K 单次观测最快：

```text
12R / 4K
0.539 s
```

但同一个配置在 32K 下明显更慢。

因此这里存在明显的：

> **context-length interaction**

也就是说：

```text
64K 表现很好的 cache 配置
≠
32K 一定也最好
```

同时 cache 表现也不是简单单调的，所以不能认为“分配得越大就一定越快”。

---

# 11. 本仓库当前的均衡推荐

参考机器目前使用：

```yaml
memory:
  sysmem_recurrent_cache: 8192
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: false
```

这**不是全局最优声明**。

选择 `8R / 4K` 是因为它在两个 context 长度都表现很好：

```text
32K cached-prefix TTFT: 0.531 s
64K cached-prefix TTFT: 0.962 s
```

同时 system RAM cache 占用比较克制。

---

# 12. 分享你的 benchmark 时建议提供什么？

```text
CPU:
GPU:
VRAM:
RAM:
OS:
NVIDIA driver:

Model:
Quantization:
Backend:
Backend version:

max_seq_len:
cache_size:
cache_mode:

cpu_moe_offload_layers:
sysmem_recurrent_cache:
sysmem_kv_cache:

Prompt target:
Actual prompt tokens:

First-pass TTFT:
First-pass prompt rate:
Decode throughput:

Cached-prefix TTFT:
重复次数:
```

例如：

```text
GPU: RTX 5070 12 GB
RAM: 96 GB
Model: Qwen3.8-Flash-Next EXL3 3.05 bpw

Context: 64K
Recurrent cache: 8 GB
KV cache: 4 GB

First-pass TTFT: 65.1 s
Prompt ingestion: ~985 tok/s
Decode: ~21 tok/s
Cached-prefix TTFT: 0.96 s
```

这样不同机器之间的数据才容易直接比较。

---

# 13. 这套 benchmark 没测什么？

它没有评价：

- 模型回答质量；
- perplexity；
- long-context retrieval accuracy；
- tool-call 正确率；
- 多用户并发；
- sustained server throughput；
- batch inference；
- KV quantization 对质量的影响。

对于 Agent 部署，最好把性能测试和功能测试一起做：

```text
structured tool calling
multi-turn tool loop
long-context exact retrieval
```

一个 benchmark 很快但 tool calling 失效的 backend，并不能算成功的 Agent 部署。

---

## 总结

在参考机器：

```text
RTX 5070 12 GB
~96 GB RAM
Qwen3.8-Flash-Next EXL3 3.05 bpw
```

我们观察到：

```text
32K–64K first-pass ingestion:
~0.9–1.0K tok/s

decode:
~20–21 tok/s

64K first-pass TTFT:
~65–70 s

完全相同 repeated-prefix TTFT:
不同 cache 配置下约 ~0.5–1.8 s
```

真正重要的不是直接照抄这里的 cache 数值。

更推荐：

> 用同一套脚本在你自己的模型、硬件和目标 context length 上测试，然后一次只调整一个 cache 参数。
