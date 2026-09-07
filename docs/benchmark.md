# Benchmarking and Local Test Guide

**English** | [简体中文](benchmark.zh-CN.md)

This page is both a **reference benchmark** and a **how-to guide** for benchmarking your own local OpenAI-compatible model.

The benchmark focuses on metrics that matter for long-context local Agent workloads:

- first-pass time to first token (TTFT);
- approximate long-prompt ingestion rate;
- decode throughput;
- exact-prefix cache reuse;
- TabbyAPI recurrent/KV system-memory cache allocation;
- CUDA allocator state (`cuda_malloc_async`).

> Most historical cache combinations below are single engineering runs. Sub-second cached-prefix TTFT is noisy; use `--runs 3` or more for serious comparisons.

---

## 1. What the benchmark does

The client is:

```text
scripts/benchmark_chat.py
```

With `--cache-reuse`, each benchmark cycle sends the same long prompt twice:

```text
first pass
└─ unique long prompt

exact-prefix reuse
└─ exact same prompt
```

The script calibrates prompt construction against **server-reported `prompt_tokens`**. Each independent cycle uses a new nonce, preventing accidental prefix reuse between cycles.

---

## 2. Metrics

### First-pass TTFT

Time from request submission until the first generated reasoning/content token arrives. For 32K–64K prompts this is dominated by prompt ingestion/prefill plus request, scheduling and first-token overhead.

### Approximate first-pass prompt rate

```text
actual_prompt_tokens / first_pass_TTFT
```

Useful for engineering comparisons, but not a pure kernel-level prefill measurement.

### Decode throughput

Approximate generation speed after the first token.

### Cached-prefix TTFT

The second request uses the exact same prompt. If the backend can restore/reuse the prefix state, TTFT may fall from tens of seconds to around one second or below.

### Effective cached-prefix rate

A cached request may produce values such as 60K or 100K tok/s when calculating `prompt_tokens / TTFT`. This is **not physical prefill speed**; the prefix is being reused rather than recomputed.

---

## 3. Quick start

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

### Repeat three independent cycles

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 64000 `
  --cache-reuse `
  --runs 3
```

The script reports a median summary when `--runs` is greater than 1.

### Generic Python

```bash
pip install openai
python scripts/benchmark_chat.py --prompt-tokens 32000 --cache-reuse --runs 3
```

---

## 4. Benchmark another local model

```powershell
python .\scripts\benchmark_chat.py `
  --base-url "http://127.0.0.1:1234/v1" `
  --model "your-local-model-id" `
  --prompt-tokens 32000 `
  --cache-reuse `
  --runs 3
```

Optional arguments:

```text
--api-key
--context-limit
--max-tokens
```

The backend must return prompt token usage during streamed calibration.

---

## 5. Recommended test sequence

For a new model/machine:

```text
short prompt
→ 8K
→ 16K
→ 32K
→ 64K
```

At each step check request completion, VRAM, system RAM, TTFT scaling and decode stability. Then enable `--cache-reuse`.

---

## 6. Tuning system-memory caches

Current known-good reference:

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

This is **not a universal optimum**.

When studying cache behavior, change one variable at a time. A useful grid is:

```text
Recurrent: 4 GB, 8 GB, 10 GB, 12 GB
KV:        4 GB, 8 GB
Allocator: false / true
```

Do not change recurrent cache, KV cache and allocator simultaneously and then attribute a difference to one variable.

After each configuration change:

```text
1. stop TabbyAPI
2. edit config.yml
3. restart TabbyAPI
4. run the same benchmark
5. record the configuration and result
```

---

## 7. Reference system

```text
OS:             Microsoft Windows 11 Education, 64-bit
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

Common model settings:

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

## 8. Reference results

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

Current allocator-enabled reference run (`10R/4K`):

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

Current allocator-enabled reference run (`10R/4K`):

```text
Actual prompt:      64,041 tokens
First-pass TTFT:    65.743 s
Cached-prefix TTFT: 0.964 s
First-pass rate:    974.1 tok/s
First-pass decode:  20.38 tok/s
Cached decode:      20.55 tok/s
```

The two earlier `10R/4K / cudaMallocAsync=false` runs were:

```text
First-pass TTFT: 65.692 / 65.185 s
Cached TTFT:     1.155 / 0.919 s
```

The allocator-enabled result falls inside the same general performance envelope. On this workload, `cuda_malloc_async=true` appears **performance-neutral within run-to-run variation**, while remaining the current known-good reference.

---

## 9. How to interpret these results

The most reproducible signal is first-pass performance:

```text
32K first-pass TTFT: ~33 s
64K first-pass TTFT: ~65–70 s
long-prompt ingestion: ~0.9–1.0K tok/s
decode: ~20–21 tok/s
```

Cached-prefix TTFT is much noisier. Historical single runs span roughly:

```text
~0.5–1.8 s at 64K
```

Cache behavior is **non-monotonic** and interacts with context length. A configuration that wins one 64K run may not be best at 32K. Do not rank configurations by a single sub-second observation to three decimal places.

For a serious comparison, use:

```text
--runs 3
```

or more and report median TTFT plus range/IQR.

---

## 10. How to report your own benchmark

Include:

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

Raw reference measurements are available in [`../benchmarks/rtx5070-12gb.csv`](../benchmarks/rtx5070-12gb.csv).

---

## 11. What this benchmark does not test

It does not measure model quality, perplexity, long-context retrieval accuracy, tool-call correctness, concurrency, batch throughput or KV-quantization quality impact.

For Agent deployment, combine speed testing with:

```text
structured tool calling
real tool execution
multi-turn tool loops
long-context exact retrieval
```

A fast backend that breaks tool calling is not a successful Agent deployment.
