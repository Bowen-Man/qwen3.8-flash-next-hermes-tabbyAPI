# Performance Tuning Guide

**English** | [简体中文](tuning.zh-CN.md)

This guide explains the main memory/performance controls for **Qwen3.8-Flash-Next EXL3 + ExLlamaV3 + TabbyAPI** on a consumer NVIDIA GPU.

Reference system:

```text
GPU:  RTX 5070 12 GB
RAM:  ~96 GB
CPU:  AMD Ryzen 9 9950X3D
Model: Qwen3.8-Flash-Next EXL3 3.05 bpw
Context: 81,920
Primary KV: FP16
```

Current known-good reference:

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

This is a practical reference, not a universal optimum.

---

## 1. Think in terms of heterogeneous memory

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

The goal is not to minimize one memory number. The goal is stable, useful Agent performance.

---

## 2. `cpu_moe_offload_layers`

Reference:

```yaml
cpu_moe_offload_layers: 999
```

This offloads all eligible MoE experts on the tested setup. It is a major reason the model is practical on 12 GB VRAM, but CPU compute, RAM bandwidth and CPU↔GPU synchronization become part of every token step.

Start high on small-VRAM systems; reduce offload only when you have measured VRAM headroom.

---

## 3. `cache_mode`

Reference:

```yaml
cache_mode: FP16
```

FP16 consumes more VRAM than quantized KV modes but avoids KV quantization. If the model fits and remains stable, there is no reason to reduce precision merely to make `nvidia-smi` look lower.

If VRAM is insufficient, benchmark supported lower-precision modes such as Q8 and re-run functional tests, especially long-context retrieval and tool loops.

---

## 4. `max_seq_len` and `cache_size`

Reference:

```yaml
max_seq_len: 81920
cache_size: 81920
```

Larger context increases runtime cache pressure. If OOM occurs, reducing context is often the cleanest fallback:

```text
81920 → 76800 → 65536
```

Hermes also needs room for system prompts, tool schemas, history and tool results, so long context is operationally useful for Agent workloads.

---

## 5. Hermes output budget

Reference:

```text
context_length = 81920
max_tokens     = 16384
```

Think of the total context budget as shared between prompt/history/tools and output. Do not set `max_tokens == context_length`.

---

## 6. `sysmem_recurrent_cache`

Reference:

```yaml
sysmem_recurrent_cache: 10240
```

This is separate from the ordinary second-tier KV cache. On hybrid/recurrent attention architectures, recurrent state can have its own system-memory cache behavior.

Do not assume larger is always faster. Historical measurements on this machine were non-monotonic and context-length dependent.

---

## 7. `sysmem_kv_cache`

Reference:

```yaml
sysmem_kv_cache: 4096
```

This is second-tier system-memory capacity for KV reuse/management. It should **not** be interpreted as simply moving 4 GB of active GPU KV permanently into RAM.

The tradeoff is roughly:

```text
recompute old state
vs
restore/reuse cached state from system RAM
```

System RAM is slower than VRAM, so more cache is not automatically faster.

---

## 8. Recurrent cache vs KV cache

Treat them as independent variables.

Bad experiment:

```text
4R/4K → 8R/8K
```

You cannot tell which change caused the result.

Better experiment:

```text
4R/4K
8R/4K
12R/4K
4R/8K
8R/8K
```

Our historical data show a strong context-length interaction: some allocations that were excellent at 64K were mediocre at 32K. Benchmark the context length you actually use.

See [`benchmark.md`](benchmark.md) for the full table.

---

## 9. `cuda_malloc_async`

Current reference:

```yaml
cuda_malloc_async: true
```

This changes CUDA device-memory allocation/reuse behavior, not the model's attention math. Its effects are more likely to appear through allocation synchronization, fragmentation or long-running stability than through a large change in raw decode speed.

On the tested `10R/4K @ 64K` workload:

```text
false run 1: first-pass 65.692 s, cached 1.155 s
false run 2: first-pass 65.185 s, cached 0.919 s
true run:    first-pass 65.743 s, cached 0.964 s
```

That is effectively performance-neutral within normal run-to-run variation. We keep `true` as the current known-good reference.

If you encounter intermittent CUDA OOM or allocator instability, test `false` while holding the rest of the configuration constant.

---

## 10. `ngram_ram`

Reference:

```yaml
ngram_ram: false
```

This keeps the Qwen n-gram data storage-backed rather than fully resident in system RAM. Use fast NVMe storage. If you have abundant free RAM, you may benchmark `true`, but do not assume it is always faster.

---

## 11. `chunk_size`

Reference:

```yaml
chunk_size: 2048
```

Chunk size can affect prompt-ingestion memory pressure and scheduling. Keep it fixed while tuning caches. Only change it after you have a stable cache baseline.

---

## 12. Benchmarking methodology

Change one variable at a time and use the same prompt target.

Recommended command:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 64000 `
  --cache-reuse `
  --runs 3
```

Prefer median first-pass TTFT and median cached-prefix TTFT over the single fastest cached result.

---

## 13. What to optimize for

Do not optimize only for minimum VRAM or the smallest single cached TTFT.

A good Agent configuration simultaneously provides:

```text
stable loading
+ acceptable first-pass TTFT
+ acceptable decode speed
+ long-context stability
+ reliable tool calling
+ enough RAM/VRAM headroom for normal use
```

For the reference machine, `10R/4K + cudaMallocAsync=true` is a current known-good operating point, not a claim of mathematical optimality.
