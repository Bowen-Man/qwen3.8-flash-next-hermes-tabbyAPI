# 性能调优指南

[English](tuning.md) | **简体中文**

本文说明 **Qwen3.8-Flash-Next EXL3 + ExLlamaV3 + TabbyAPI** 在消费级 NVIDIA GPU 上最重要的内存/性能参数。

参考机器：

```text
GPU:  RTX 5070 12 GB
RAM:  ~96 GB
CPU:  AMD Ryzen 9 9950X3D
Model: Qwen3.8-Flash-Next EXL3 3.05 bpw
Context: 81,920
Primary KV: FP16
```

当前 known-good reference：

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

它是工程参考，不是全局最优。

---

## 1. 用异构内存思维理解

```text
GPU VRAM
├── GPU-resident model components
├── attention compute
├── active / primary KV state
└── runtime buffers

System RAM
├── CPU-offloaded MoE experts
├── recurrent cache
├── second-tier KV cache
└── runtime / OS memory

NVMe SSD
└── n-gram embedding data
```

目标不是把某一个内存数字降到最低，而是得到稳定、实用的 Agent 性能。

---

## 2. `cpu_moe_offload_layers`

参考：

```yaml
cpu_moe_offload_layers: 999
```

在参考配置里相当于把可 offload 的 MoE experts 都交给 CPU。这是 12 GB VRAM 能运行大 MoE 模型的重要原因，但 CPU compute、RAM bandwidth 和 CPU↔GPU synchronization 会进入每个 token 的推理路径。

小显存系统建议从高 offload 开始，只有在确认显存有明显余量后再减少。

---

## 3. `cache_mode`

参考：

```yaml
cache_mode: FP16
```

FP16 比量化 KV 更占显存，但不引入 KV quantization。如果模型已经能稳定运行，不需要为了让 `nvidia-smi` 数字更低就主动降精度。

显存不足时再测试 Q8 等支持的模式，同时重新验证 long-context retrieval 和 tool loop。

---

## 4. `max_seq_len` 与 `cache_size`

参考：

```yaml
max_seq_len: 81920
cache_size: 81920
```

context 越大，runtime cache 压力越高。遇到 OOM 时，一个很干净的 fallback 是：

```text
81920 → 76800 → 65536
```

Hermes 还需要容纳 system prompt、tool schema、history 和 tool results，所以长 context 对 Agent 很有实际意义。

---

## 5. Hermes 输出预算

参考：

```text
context_length = 81920
max_tokens     = 16384
```

总 context 需要在输入和输出之间共享，不要设置 `max_tokens == context_length`。

---

## 6. `sysmem_recurrent_cache`

参考：

```yaml
sysmem_recurrent_cache: 10240
```

它和普通 second-tier KV cache 是两个不同参数。对于 hybrid/recurrent attention 架构，recurrent state 有自己的 system-memory cache 行为。

不要假设越大越快。本机历史实验明显是非单调的，而且会随 context length 改变。

---

## 7. `sysmem_kv_cache`

参考：

```yaml
sysmem_kv_cache: 4096
```

它是 system RAM 中用于 KV reuse/management 的二级容量，**不能**简单理解成“把 4 GB active GPU KV 永久搬到 RAM”。

大致 tradeoff：

```text
重新计算旧状态
vs
从 system RAM 恢复/复用旧状态
```

RAM 比 VRAM 慢，所以 cache 更大不等于更快。

---

## 8. Recurrent cache 与 KV cache 要分开调

不好的实验：

```text
4R/4K → 8R/8K
```

因为你不知道是哪一个变量产生作用。

更好的矩阵：

```text
4R/4K
8R/4K
12R/4K
4R/8K
8R/8K
```

我们的历史数据还显示明显的 context-length interaction：64K 很好的配置，在 32K 未必最好。

完整数据见 [`benchmark.zh-CN.md`](benchmark.zh-CN.md)。

---

## 9. `cuda_malloc_async`

当前 reference：

```yaml
cuda_malloc_async: true
```

它改变的是 CUDA device memory 的 allocation/reuse 行为，而不是 attention 数学本身。其价值更可能体现在 allocation synchronization、fragmentation 或长期稳定性，而不是让 decode 突然大幅变快。

本机 `10R/4K @ 64K`：

```text
false run 1: first-pass 65.692 s, cached 1.155 s
false run 2: first-pass 65.185 s, cached 0.919 s
true run:    first-pass 65.743 s, cached 0.964 s
```

所以速度上基本落在正常 run-to-run variation 内。我们保留 `true` 作为当前 known-good reference。

如果出现 intermittent CUDA OOM 或 allocator instability，再固定其他参数、单独测试 `false`。

---

## 10. `ngram_ram`

参考：

```yaml
ngram_ram: false
```

让 Qwen n-gram 数据保持 storage-backed，而不是全部驻留 RAM。建议使用快 NVMe。如果空闲 RAM 很多，可以 benchmark `true`，但不要默认它一定更快。

---

## 11. `chunk_size`

参考：

```yaml
chunk_size: 2048
```

chunk size 会影响 prompt ingestion 的 memory pressure 和 scheduling。调 cache 时先保持它不变，等 cache baseline 稳定后再研究。

---

## 12. 正确 benchmark 方法

一次只改一个变量，并保持 prompt target 一样。

推荐：

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 64000 `
  --cache-reuse `
  --runs 3
```

优先比较 median first-pass TTFT 和 median cached-prefix TTFT，不要只挑单次最快的 cached 结果。

---

## 13. 到底优化什么？

不要只追求最低 VRAM 或最小的一次 cached TTFT。

好的 Agent 配置应该同时满足：

```text
稳定加载
+ 可接受 first-pass TTFT
+ 可接受 decode
+ long-context 稳定
+ tool calling 可靠
+ 日常使用仍有 RAM/VRAM 余量
```

对参考机器而言，`10R/4K + cudaMallocAsync=true` 是当前 known-good operating point，不是数学意义上的最优解。
