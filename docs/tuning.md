# Performance Tuning Guide

**English** | [简体中文](tuning.zh-CN.md)

This document explains the main performance and memory tradeoffs for running **Qwen3.8-Flash-Next EXL3 + ExLlamaV3 + TabbyAPI** on a consumer NVIDIA GPU.

The tested system uses:

```text
GPU: 12 GB VRAM
RAM: 96 GB
CPU: AMD Ryzen 9 9950X3D
Model: Qwen3.8-Flash-Next EXL3 3.05 bpw
Context: 81,920
Primary KV cache: FP16
System-memory KV cache: 2048 MB
CPU MoE offload: all eligible layers
```

This is a practical tuning reference, not a universal optimum.

---

# 1. Think in terms of heterogeneous memory

This setup does not try to fit the entire model into VRAM.

Instead:

```text
GPU VRAM
├── GPU-resident model components
├── attention compute
├── active / primary KV cache
└── runtime buffers

System RAM
├── CPU-offloaded MoE experts
└── second-tier KV cache

NVMe SSD
└── n-gram embedding table
```

The goal is to keep latency-sensitive work on the GPU while moving capacity-heavy components to RAM or SSD.

---

# 2. `cpu_moe_offload_layers`

Tested value:

```yaml
cpu_moe_offload_layers: 999
```

A large value such as `999` offloads all eligible MoE layers to CPU inference.

This is one of the most important settings for small-VRAM systems.

## Benefits

- dramatically reduces VRAM pressure;
- allows very large MoE models to run on consumer GPUs;
- makes good use of systems with large RAM and strong CPUs.

## Costs

- CPU compute becomes part of every token-generation step;
- RAM bandwidth matters;
- CPU↔GPU synchronization may become a bottleneck;
- decode speed can be lower than a GPU-heavy configuration.

## Recommendation

For 12 GB VRAM, start with:

```yaml
cpu_moe_offload_layers: 999
```

Only reduce CPU offload if you have clear VRAM headroom.

---

# 3. `cache_mode`

Tested value:

```yaml
cache_mode: FP16
```

FP16 provides a high-quality KV cache but consumes more VRAM than quantized cache modes.

If the model fits and remains stable, FP16 is a reasonable default.

If VRAM is insufficient, consider:

```yaml
cache_mode: Q8
```

or other supported quantized cache modes.

## Tradeoff

```text
FP16
→ more VRAM
→ no KV quantization

Q8 / lower-bit cache
→ less VRAM
→ potentially slightly different quality / performance characteristics
```

Do not change cache precision only to reduce an already-safe VRAM number.

---

# 4. `cache_size` and `max_seq_len`

Tested values:

```yaml
max_seq_len: 81920
cache_size: 81920
```

These settings define the practical context capacity exposed by the server.

Larger context means more cache memory.

If you encounter out-of-memory errors, reducing context is usually one of the cleanest ways to regain VRAM.

Suggested fallback sequence:

```text
81920
↓
76800
↓
65536
```

For an Agent workload, 65K+ context is still useful because tool schemas, history and tool results can consume substantial prompt space.

---

# 5. Hermes output budget

Tested Hermes configuration:

```text
context_length = 81920
max_tokens     = 16384
```

The output budget must leave room for the input prompt.

A useful mental model:

```text
81,920 total
├── ~65,536 prompt / history / tools
└── ≤16,384 generation
```

Avoid:

```text
max_tokens == context_length
```

because the request then leaves no budget for the actual prompt.

---

# 6. `sysmem_kv_cache`

Tested value:

```yaml
memory:
  sysmem_kv_cache: 2048
```

This provides approximately 2 GB of second-tier KV cache in system RAM.

On the tested system, static dedicated GPU memory after model loading was approximately:

```text
10.5 GB / 12 GB
```

## Important

This is not simply:

```text
VRAM KV - 2 GB = RAM KV
```

It is a second-tier cache mechanism.

The main benefits are related to cache management and reuse.

## Why not make it extremely large?

More RAM cache is not automatically faster.

A reused KV state may need to move from system RAM back toward the GPU path.

The tradeoff is approximately:

```text
recompute KV
vs
restore/reuse KV from RAM
```

For long repeated prefixes, reuse may help.

For short prompts or low reuse, a very large second-tier cache may provide little benefit.

---

# 7. `ngram_ram`

Tested value:

```yaml
ngram_ram: false
```

Qwen3.8-Flash-Next uses an n-gram embedding table.

With `false`, the table is streamed from storage instead of being fully loaded into RAM.

This reduces RAM pressure.

## Recommendation

Use a fast NVMe SSD.

If you have very large amounts of free RAM, you may benchmark `ngram_ram: true`, but do not assume it will be universally better.

---

# 8. `chunk_size`

Tested value:

```yaml
chunk_size: 2048
```

This affects prompt ingestion.

General direction:

```text
larger chunk
→ faster prefill in some cases
→ potentially more VRAM pressure

smaller chunk
→ lower peak memory
→ potentially slower ingestion
```

A practical test range is:

```text
1024
2048
4096
```

For the tested 12 GB system, `2048` is a reasonable baseline.

---

# 9. `max_batch_size`

Tested value:

```yaml
max_batch_size: 1
```

For a single-user local Agent, concurrency is usually unnecessary.

Using:

```yaml
max_batch_size: 1
```

minimizes memory overhead.

Increase this only if you intentionally need concurrent requests.

---

# 10. `output_chunking`

Tested value:

```yaml
output_chunking: true
```

This allows cache/output allocation to grow in chunks rather than allocating the entire completion budget immediately.

For a VRAM-limited local deployment, leaving this enabled is sensible.

---

# 11. What to optimize first

If the model does not fit:

```text
1. Keep CPU MoE offloading high
2. Reduce context size
3. Consider quantized KV cache
4. Reduce chunk size
5. Avoid unnecessary batch concurrency
```

If the model fits but is slow:

```text
1. Measure decode tok/s
2. Measure TTFT / prefill
3. Check CPU utilization
4. Check RAM bandwidth pressure
5. Check SSD activity
6. Only then move more work back to GPU
```

Do not optimize based only on Task Manager memory numbers.

---

# 12. What to benchmark

For Agent workloads, useful metrics include:

| Metric | Why it matters |
|---|---|
| Static VRAM after load | capacity / safety margin |
| RAM usage after load | CPU-offload footprint |
| Time to first token (TTFT) | user-perceived latency |
| Prefill speed | long-context performance |
| Decode tok/s | generation speed |
| 8K prompt TTFT | short/medium context |
| 32K prompt TTFT | long Agent history |
| 64K prompt TTFT | near-context-limit behavior |
| Tool-call success rate | Agent reliability |
| Repeated-prefix TTFT | KV-cache reuse effectiveness |

---

# 13. Benchmark template

Use the same prompt and model configuration for each comparison.

| Config | Static VRAM | Free RAM | Context | KV mode | sysmem KV | TTFT | Decode tok/s | Tool call |
|---|---:|---:|---:|---|---:|---:|---:|---|
| Baseline | | | 81920 | FP16 | 2048 MB | | | ✅ |
| Variant A | | | | | | | | |
| Variant B | | | | | | | | |

When changing one parameter, keep all other parameters fixed.

---

# 14. A useful tuning principle

The optimization problem changes as the model starts to fit.

At first:

```text
main problem = capacity
```

After the model fits:

```text
main problem = data movement + compute balance
```

On a heterogeneous setup, performance depends on:

```text
GPU compute
+
CPU compute
+
RAM bandwidth
+
CPU↔GPU transfer
+
SSD access
```

This is why more offloading, more cache or more RAM usage is not automatically faster.

---

# 15. Current tested baseline

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
  sysmem_kv_cache: 2048
```

Observed on the tested machine:

```text
Static dedicated VRAM after loading: ~10.5 GB / 12 GB
```

Treat this as a reference point rather than a guaranteed result.

---

# 16. Final recommendation

For a 12 GB GPU with abundant system RAM:

```text
Start stable
→ verify tool calling
→ measure real Agent workloads
→ change one parameter at a time
```

A configuration that uses more RAM or less VRAM is not necessarily better.

The best configuration is the one that simultaneously provides:

```text
stable model loading
+
acceptable TTFT
+
acceptable decode speed
+
long-context stability
+
reliable tool calling
```
