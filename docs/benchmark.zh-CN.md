# Benchmark 与本地测试指南

[English](benchmark.md) | **简体中文**

这一页既是本仓库的**参考 benchmark**，也是一份告诉你如何测试自己本地 OpenAI-compatible 模型的指南。

重点指标：

- first-pass TTFT；
- long-prompt ingestion；
- decode throughput；
- exact-prefix cache reuse；
- TabbyAPI recurrent/KV system-memory cache；
- CUDA allocator (`cuda_malloc_async`)。

> 历史 cache 组合大多是单次工程测试。亚秒级 cached-prefix TTFT 波动较大，正式比较建议使用 `--runs 3` 或更多次。

---

## 1. Benchmark 在做什么？

脚本：

```text
scripts/benchmark_chat.py
```

使用 `--cache-reuse` 时，每个 benchmark cycle 会发送同一段长 prompt 两次：

```text
first pass
└─ 带唯一 nonce 的长 prompt

exact-prefix reuse
└─ 完全相同的 prompt
```

脚本先依据 server 返回的 `prompt_tokens` 做 calibration；不同独立 cycle 会生成新的 nonce，避免 cycle 之间意外复用 prefix。

---

## 2. 指标解释

### First-pass TTFT

从请求发出到第一个 reasoning/content token 到达的时间。32K–64K 下主要由 prompt ingestion/prefill，加上请求、调度和首 token 开销组成。

### Approximate first-pass prompt rate

```text
actual_prompt_tokens / first_pass_TTFT
```

适合工程比较，但不是纯 kernel-level prefill benchmark。

### Decode throughput

首 token 之后的近似生成速度。

### Cached-prefix TTFT

第二个请求使用完全相同的 prompt。如果 backend 可以恢复/复用 prefix state，TTFT 可以从几十秒下降到约 1 秒甚至更低。

### Effective cached-prefix rate

cached run 可能显示 60K、100K tok/s。这**不是物理 prefill 速度**，因为大部分 prefix 并未重算，而是被复用。

---

## 3. 快速测试

### Windows + Hermes Python

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 32000 `
  --cache-reuse
```

### 64K

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 64000 `
  --cache-reuse
```

### 独立重复 3 次

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 64000 `
  --cache-reuse `
  --runs 3
```

`--runs > 1` 时脚本会输出 median summary。

### 普通 Python

```bash
pip install openai
python scripts/benchmark_chat.py --prompt-tokens 32000 --cache-reuse --runs 3
```

---

## 4. 测其他本地模型

```powershell
python .\scripts\benchmark_chat.py `
  --base-url "http://127.0.0.1:1234/v1" `
  --model "your-local-model-id" `
  --prompt-tokens 32000 `
  --cache-reuse `
  --runs 3
```

可选：

```text
--api-key
--context-limit
--max-tokens
```

backend 需要在 streamed calibration 中返回 prompt token usage。

---

## 5. 推荐测试顺序

新机器/新模型不要直接上 64K：

```text
短 prompt
→ 8K
→ 16K
→ 32K
→ 64K
```

每一步观察请求是否完成、VRAM、RAM、TTFT scaling 和 decode 稳定性，然后再加 `--cache-reuse`。

---

## 6. 调 system-memory cache

当前 known-good reference：

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

这**不是全局最优**。

研究 cache 时一次只改一个变量。可以用：

```text
Recurrent: 4 GB, 8 GB, 10 GB, 12 GB
KV:        4 GB, 8 GB
Allocator: false / true
```

不要同时改 recurrent、KV 和 allocator，然后只把结果归因给其中一个。

每改一次配置：

```text
1. 停 TabbyAPI
2. 修改 config.yml
3. 重启 TabbyAPI
4. 跑同一个 benchmark
5. 保存配置与结果
```

---

## 7. 参考机器

```text
OS:             Microsoft Windows 11 教育版，64-bit
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

公共 model 设置：

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
```

---

## 8. 实测结果

### 32K

| Recurrent | KV | cudaMallocAsync | First-pass TTFT | Cached TTFT | First-pass rate |
|---:|---:|:---:|---:|---:|---:|
| 4 GB | 4 GB | false | 33.539 s | 0.899 s | ~955 tok/s |
| 4 GB | 8 GB | false | 33.344 s | 1.340 s | ~959 tok/s |
| 8 GB | 4 GB | false | 32.773 s | **0.531 s** | ~977 tok/s |
| 8 GB | 8 GB | false | 35.288 s | 0.765 s | ~908 tok/s |
| 12 GB | 4 GB | false | 33.301 s | 1.396 s | ~961 tok/s |
| 12 GB | 12 GB | false | 33.403 s | 1.390 s | ~957 tok/s |
| **10 GB** | **4 GB** | **true** | **33.248 s** | **0.738 s** | **~964 tok/s** |

当前 allocator-enabled reference (`10R/4K`)：

```text
Actual prompt:       32,038 tokens
First-pass TTFT:     33.248 s
Cached-prefix TTFT:  0.738 s
First-pass rate:     963.6 tok/s
First-pass decode:   21.13 tok/s
Observed VRAM after: 11,186 / 12,227 MiB
```

### 64K

| Recurrent | KV | cudaMallocAsync | Run | First-pass TTFT | Cached TTFT | First-pass rate |
|---:|---:|:---:|:---:|---:|---:|---:|
| 4 GB | 4 GB | false | 1 | 70.255 s | 1.813 s | ~910 tok/s |
| 4 GB | 8 GB | false | 1 | 65.403 s | 0.660 s | ~979 tok/s |
| 8 GB | 4 GB | false | 1 | 65.057 s | 0.962 s | ~985 tok/s |
| 8 GB | 8 GB | false | 1 | 70.215 s | 1.029 s | ~912 tok/s |
| 10 GB | 4 GB | false | 1 | 65.692 s | 1.155 s | 975.6 tok/s |
| 10 GB | 4 GB | false | 2 | 65.185 s | 0.919 s | 982.4 tok/s |
| 12 GB | 4 GB | false | 1 | 66.491 s | **0.539 s** | ~963 tok/s |
| 12 GB | 12 GB | false | 1 | 65.103 s | 1.062 s | ~984 tok/s |
| **10 GB** | **4 GB** | **true** | **1** | **65.743 s** | **0.964 s** | **974.1 tok/s** |

当前 allocator-enabled reference (`10R/4K`)：

```text
Actual prompt:      64,041 tokens
First-pass TTFT:    65.743 s
Cached-prefix TTFT: 0.964 s
First-pass rate:    974.1 tok/s
First-pass decode:  20.38 tok/s
Cached decode:      20.55 tok/s
```

此前两次 `10R/4K / cudaMallocAsync=false`：

```text
First-pass TTFT: 65.692 / 65.185 s
Cached TTFT:     1.155 / 0.919 s
```

`true` 的结果落在同一个总体性能区间内。因此在当前 workload 下，`cuda_malloc_async=true` **没有显示明确速度增益，也没有明显性能惩罚**；我们把它作为当前 known-good reference 保留。

---

## 9. 如何理解结果

最稳定的是 first-pass：

```text
32K first-pass TTFT: ~33 s
64K first-pass TTFT: ~65–70 s
long-prompt ingestion: ~0.9–1.0K tok/s
decode: ~20–21 tok/s
```

cached-prefix TTFT 波动明显更大，64K 历史单次值大约：

```text
~0.5–1.8 s
```

cache 行为**不是单调的**，而且与 context length 存在 interaction。不要用某个单次 0.xxx s 的结果精确排名配置。

正式比较建议：

```text
--runs 3
```

或更多，并报告 median + range/IQR。

---

## 10. 分享你自己的 benchmark

建议包含：

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
cuda_malloc_async:

Prompt target:
Actual prompt tokens:
First-pass TTFT:
First-pass prompt rate:
Decode throughput:
Cached-prefix TTFT:
Independent runs:
```

参考原始数据：[`../benchmarks/rtx5070-12gb.csv`](../benchmarks/rtx5070-12gb.csv)。

---

## 11. 这套 benchmark 没测什么？

它不评价模型质量、perplexity、long-context retrieval accuracy、tool-call correctness、并发、batch throughput 或 KV quantization 对质量的影响。

Agent 部署应该把速度和功能验证一起做：

```text
structured tool calling
real tool execution
multi-turn tool loops
long-context exact retrieval
```

一个很快但 tool calling 失效的 backend，并不能算成功的 Agent 部署。
