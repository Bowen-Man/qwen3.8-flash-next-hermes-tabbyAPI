# Benchmarking

[**English**](benchmark.md) | [简体中文](benchmark.zh-CN.md)

This page is both a **reference benchmark** for this repository and a **how-to guide** for benchmarking your own local model.

The benchmark focuses on metrics that matter for long-context local Agent workloads:

- first-pass time to first token (TTFT);
- approximate long-prompt ingestion rate;
- decode throughput;
- exact-prefix cache reuse;
- TabbyAPI system-memory recurrent/KV cache behavior.

> Most cache configurations below are single engineering runs. For rigorous comparisons, repeat each configuration at least three times and report a median.

---

## 1. Benchmark method

The benchmark client is:

```text
scripts/benchmark_chat.py
```

With `--cache-reuse`, the script sends the same long prompt twice:

```text
Run 1
└─ unique long prompt
   └─ first-pass processing

Run 2
└─ exact same prompt
   └─ repeated-prefix / cache-reuse test
```

The script first calibrates prompt construction against **server-reported token usage**, then builds a synthetic prompt close to the requested target.

Each independent invocation contains a unique nonce so that separate benchmark runs do not intentionally reuse the previous long prefix.

---

## 2. Metrics

### First-pass TTFT

Time from request submission until the first generated token arrives.

For a 32K–64K prompt this is dominated by prompt ingestion / prefill.

```text
lower = better
```

### Approximate first-pass prompt rate

Calculated as:

```text
actual_prompt_tokens / first_pass_TTFT
```

For first-pass requests this is a useful engineering approximation of long-prompt ingestion performance.

It is not a pure kernel-level prefill benchmark because TTFT also includes request, scheduling, template and first-token overhead.

### Decode throughput

Approximate generation speed after the first token.

```text
completion tokens / generation time
```

### Cached-prefix TTFT

The second request uses the exact same prompt. If the backend can reuse the previous prefix state, TTFT can fall from tens of seconds to around one second or less.

This is especially relevant for Agent workloads that repeatedly carry a large:

```text
system prompt
tool schema
conversation history
fixed context prefix
```

### Do not interpret cached prompt/TTFT rate as physical prefill speed

A cached run may print values such as:

```text
60K tok/s
100K tok/s
```

That does **not** mean the model recomputed the whole prompt at that rate.

For cached runs, interpret:

```text
prompt_tokens / TTFT
```

only as an **effective cached-prefix reuse rate**.

---

## 3. Requirements

You need:

- a running OpenAI-compatible local endpoint;
- Python with the `openai` package;
- `scripts/benchmark_chat.py`.

Repository defaults:

```text
Base URL: http://127.0.0.1:8088/v1
Model:    Qwen3.8-Flash-Next-exl3-3.05bpw
```

---

## 4. Quick start

### Windows + Hermes Python

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py"
```

### 32K

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 32000
```

### 32K with cache reuse

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 32000 `
  --cache-reuse
```

### 64K with cache reuse

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\benchmark_chat.py" `
  --prompt-tokens 64000 `
  --cache-reuse
```

### Generic Python environment

```bash
pip install openai
python scripts/benchmark_chat.py --prompt-tokens 32000 --cache-reuse
```

---

## 5. Benchmark another local model

Point the script at another OpenAI-compatible endpoint:

```powershell
python .\scripts\benchmark_chat.py `
  --base-url "http://127.0.0.1:1234/v1" `
  --model "your-local-model-id" `
  --prompt-tokens 32000 `
  --cache-reuse
```

This can be used with OpenAI-compatible local backends such as TabbyAPI, LM Studio, vLLM, llama.cpp servers and similar systems, provided the backend returns token usage during calibration.

---

## 6. Recommended testing sequence

For a new machine or model, start small:

```text
short prompt
→ 8K
→ 16K
→ 32K
→ 64K
```

At each step check:

```text
Does the request finish?
Is VRAM stable?
Does system RAM remain under control?
Does TTFT scale reasonably?
Does decode throughput remain stable?
```

Then add:

```text
--cache-reuse
```

to measure repeated-prefix behavior.

---

## 7. How to tune TabbyAPI system-memory caches

Relevant settings:

```yaml
memory:
  sysmem_recurrent_cache: 8192
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: false
```

The most important rule is:

> Change one variable at a time.

Do not compare:

```text
4R / 4K
→
8R / 8K
```

and attribute the difference to only one cache.

A better grid is:

```text
Recurrent: 4 GB, 8 GB, 12 GB
KV:        4 GB, 8 GB
```

For example:

```text
4R / 4K
8R / 4K
12R / 4K
4R / 8K
8R / 8K
```

After every change:

```text
1. stop TabbyAPI
2. edit config.yml
3. restart TabbyAPI
4. run the benchmark
5. record the result
```

When tuning cache allocation, keep other settings fixed where possible:

```text
cache_mode
chunk_size
max_seq_len
CPU offload
CUDA allocator
```

---

## 8. Improving reliability

Sub-second cached-prefix TTFT is sensitive to runtime state.

Possible sources of variation include:

- Windows scheduling;
- allocator state;
- CPU/RAM pressure;
- cache residency;
- background applications;
- storage activity;
- previous inference state.

For a serious comparison, run each configuration at least three times and report:

```text
median TTFT
range or IQR
```

First-pass TTFT is generally more stable than cached-prefix TTFT.

---

# 9. Reference system

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

Common inference settings:

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

# 10. Reference results

## 32K prompt

| Recurrent | KV | First-pass TTFT | Cached-prefix TTFT | First-pass rate |
|---:|---:|---:|---:|---:|
| 4 GB | 4 GB | 33.539 s | 0.899 s | ~955 tok/s |
| 4 GB | 8 GB | 33.344 s | 1.340 s | ~959 tok/s |
| **8 GB** | **4 GB** | **32.773 s** | **0.531 s** | **~977 tok/s** |
| 8 GB | 8 GB | 35.288 s | 0.765 s | ~908 tok/s |
| 12 GB | 4 GB | 33.301 s | 1.396 s | ~961 tok/s |
| 12 GB | 12 GB | 33.403 s | 1.390 s | ~957 tok/s |

Observed first-pass range:

```text
TTFT:       ~32.8–35.3 s
ingestion:  ~0.91–0.98K tok/s
decode:     ~20–21 tok/s
```

Best observed single-run 32K cached-prefix result:

```text
8R / 4K
0.531 s
```

---

## 64K prompt

| Recurrent | KV | First-pass TTFT | Cached-prefix TTFT | First-pass rate |
|---:|---:|---:|---:|---:|
| 4 GB | 4 GB | 70.255 s | 1.813 s | ~910 tok/s |
| 4 GB | 8 GB | 65.403 s | 0.660 s | ~979 tok/s |
| **8 GB** | **4 GB** | **65.057 s** | **0.962 s** | **~985 tok/s** |
| 8 GB | 8 GB | 70.215 s | 1.029 s | ~912 tok/s |
| 10 GB | 4 GB | 65.692 / 65.185 s | 1.155 / 0.919 s | ~979 tok/s |
| 12 GB | 4 GB | 66.491 s | **0.539 s** | ~963 tok/s |
| 12 GB | 12 GB | 65.103 s | 1.062 s | ~984 tok/s |

The 10R / 4K configuration was measured twice:

```text
First-pass TTFT:
65.692 s
65.185 s

Cached-prefix TTFT:
1.155 s
0.919 s

Average first-pass TTFT:
~65.44 s

Average cached-prefix TTFT:
~1.04 s
```

Observed 64K first-pass range:

```text
TTFT:       ~65–70 s
ingestion:  ~0.91–0.98K tok/s
decode:     ~20–21 tok/s
```

Best observed single-run 64K cached-prefix result:

```text
12R / 4K
0.539 s
```

However, the same configuration was much slower at 32K.

This shows a clear **context-length interaction**:

> A cache allocation that performs very well at 64K is not necessarily the best at 32K.

Cache behavior is also non-monotonic, so a larger system-memory cache should not automatically be assumed to be faster.

---

# 11. Balanced configuration used by this repository

For the reference machine, a reasonable balanced default is:

```yaml
memory:
  sysmem_recurrent_cache: 8192
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: false
```

This is **not claimed to be a universal optimum**.

It was selected because it was strong at both tested context lengths:

```text
32K cached-prefix TTFT: 0.531 s
64K cached-prefix TTFT: 0.962 s
```

while keeping system-memory cache allocation moderate.

---

# 12. How to report your own benchmark

When comparing machines or opening an issue, include:

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
Number of repeated runs:
```

Example:

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

---

# 13. What this benchmark does not test

This benchmark does not measure:

- model quality;
- perplexity;
- long-context retrieval accuracy;
- tool-call correctness;
- multi-user concurrency;
- sustained server throughput;
- batch inference;
- KV-quantization quality impact.

For Agent deployment, combine performance testing with functional tests such as:

```text
structured tool calling
multi-turn tool loops
long-context exact retrieval
```

A fast backend that breaks tool calling is not a successful Agent deployment.

---

## Bottom line

On the reference RTX 5070 12 GB / ~96 GB RAM machine, Qwen3.8-Flash-Next EXL3 3.05 bpw showed approximately:

```text
32K–64K first-pass ingestion:
~0.9–1.0K tok/s

decode:
~20–21 tok/s

64K first-pass TTFT:
~65–70 s

exact repeated-prefix TTFT:
~0.5–1.8 s across the tested cache configurations
```

The main recommendation is **not** to blindly copy these cache values.

Use the same benchmark script on your own model, hardware and target context length, and tune one cache parameter at a time.
