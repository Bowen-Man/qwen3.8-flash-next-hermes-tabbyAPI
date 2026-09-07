# Qwen3.8-Flash-Next + Hermes Agent via TabbyAPI

**English** | [简体中文](README.zh-CN.md)

Run **Qwen3.8-Flash-Next EXL3** as a local backend for **Hermes Agent** using **ExLlamaV3 + TabbyAPI**, with native OpenAI-compatible structured tool calling on a consumer NVIDIA GPU.

This repository documents a tested **Windows + consumer NVIDIA GPU** deployment path. The reference system is an **RTX 5070 12 GB + 96 GB RAM** workstation running the **Qwen3.8-Flash-Next EXL3 3.05 bpw** quantization.

> The configuration in this repository is a **known-good reference**, not a universal optimum. Cache/offload settings should be benchmarked on your own hardware and target context length.

## What is validated

- Qwen3.8-Flash-Next EXL3 inference with ExLlamaV3;
- TabbyAPI OpenAI-compatible `/v1/chat/completions`;
- 81,920-token server context with FP16 primary KV cache;
- CPU MoE expert offloading and disk-backed n-gram data;
- native structured OpenAI `tool_calls` via `tool_format: qwen3_coder`;
- real Hermes Agent tool execution;
- reproducible 32K / 64K long-context and cache-reuse benchmarking.

---

## Quick Start

The complete setup guide is in:

[`docs/installation.md`](docs/installation.md)

Deployment flow:

```text
1. Prepare the Qwen3.8-Flash-Next EXL3 model
2. Install TabbyAPI + ExLlamaV3
3. Copy and edit config/config.example.yml
4. Start TabbyAPI
5. Verify structured tool calling
6. Connect Hermes Agent
7. Verify real Hermes tool execution
8. Benchmark your own hardware
```

Start TabbyAPI:

```powershell
cd E:\tabbyAPI
& ".\venv\Scripts\python.exe" .\main.py
```

Verify the API:

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

Verify native structured tool calling. If your global Python environment does not have the OpenAI SDK, use Hermes' Python:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

Expected result:

```text
Finish reason: tool_calls
PASS: Structured tool calling works.
```

Then configure Hermes:

```text
Provider:              Custom endpoint
API compatibility:     Chat Completions
Base URL:              http://127.0.0.1:8088/v1
Model:                 Qwen3.8-Flash-Next-exl3-3.05bpw
Context length:        81920
Maximum output tokens: 16384
```

Finally run the real Agent-side tool test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_hermes_tool.ps1
# or
Unblock-File .\scripts\test_hermes_tool.ps1
```

---

## Documentation

### Installation

[`docs/installation.md`](docs/installation.md)

Complete Windows setup:

```text
EXL3 model
→ ExLlamaV3
→ TabbyAPI
→ structured tool_calls
→ Hermes Agent
```

### Configuration

[`config/config.example.yml`](config/config.example.yml)

Current known-good reference on the test machine:

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

Other important settings include:

```text
81,920-token context
FP16 primary KV cache
CPU MoE offloading
NVMe-backed n-gram data
qwen3_coder tool parsing
```

### Benchmarking

[`docs/benchmark.md`](docs/benchmark.md)

The benchmark guide explains how to test **your own OpenAI-compatible local model**, including:

- 8K / 16K / 32K / 64K prompt targets;
- first-pass TTFT;
- approximate long-prompt ingestion rate;
- decode throughput;
- exact-prefix cache reuse;
- recurrent/KV system-memory cache tuning;
- repeated-run median reporting.

Reference raw measurements are stored in:

[`benchmarks/rtx5070-12gb.csv`](benchmarks/rtx5070-12gb.csv)

### Performance tuning

[`docs/tuning.md`](docs/tuning.md)

Covers MoE offload, FP16/Q8 KV choices, recurrent cache, second-tier KV cache, context size, `cuda_malloc_async`, and how to tune one variable at a time.

### Tool-call verification

[`scripts/test_tool_call.py`](scripts/test_tool_call.py)

Tests the serving layer independently:

```text
OpenAI client
→ TabbyAPI
→ Qwen3.8-Flash-Next
→ qwen3_coder parser
→ structured OpenAI tool_calls
```

[`scripts/test_hermes_tool.ps1`](scripts/test_hermes_tool.ps1) verifies the next layer by forcing Hermes to read an unpredictable UUID from a temporary file.
(After `Unblock-File .\scripts\test_hermes_tool.ps1` / `powershell -ExecutionPolicy Bypass -File .\scripts\test_hermes_tool.ps1`)

### Troubleshooting

[`docs/troubleshooting.md`](docs/troubleshooting.md)

Covers proxy issues, Python/OpenAI SDK mismatches, tool calls returning plain text, Torch/CUDA installation failures, context-budget errors, RAM/VRAM behavior, recurrent/KV cache behavior, and allocator-related OOM troubleshooting.

---

## Benchmark snapshot

Reference machine:

```text
OS:          Windows 11
CPU:         AMD Ryzen 9 9950X3D
GPU:         NVIDIA GeForce RTX 5070 12 GB
RAM:         96 GB
Model:       Qwen3.8-Flash-Next EXL3 3.05 bpw
Context:     81,920
Primary KV:  FP16
```

Current `10R / 4K / cudaMallocAsync=true` measurements:

| Prompt | First-pass TTFT | Cached-prefix TTFT | First-pass rate | Decode |
|---:|---:|---:|---:|---:|
| 32K | 33.248 s | 0.738 s | ~964 tok/s | ~21.1 tok/s |
| 64K | 65.743 s | 0.964 s | ~974 tok/s | ~20.4 tok/s |

Across the broader cache experiments, 64K first-pass ingestion was generally around **0.9–1.0K tok/s**, while exact repeated prefixes reduced TTFT from roughly **65–70 s** to about **0.5–1.8 s**, depending on cache allocation and runtime state.

Do not interpret cached `prompt_tokens / TTFT` as physical prefill throughput; it is an effective cache-reuse rate.

---

## Why this repository exists

An OpenAI-compatible `/v1/chat/completions` endpoint does **not** automatically imply OpenAI-compatible tool calling.

A minimal server may handle:

```text
messages
→ model
→ assistant content
```

while ignoring or mishandling:

```text
tools
tool_choice
tool_calls
```

In the initial setup, the model could reason that a tool should be used, while Hermes still reported zero tool calls. The missing layer was the serving stack.

With TabbyAPI and:

```yaml
tool_format: qwen3_coder
```

the complete path becomes:

```text
Hermes Agent
   ↓
OpenAI Chat Completions API
   ↓
TabbyAPI
   ↓
Qwen tool schema / chat template
   ↓
ExLlamaV3
   ↓
Qwen3.8-Flash-Next
   ↓
qwen3_coder tool-call output
   ↓
TabbyAPI parser
   ↓
OpenAI tool_calls
   ↓
Hermes executes the tool
```

---

## Memory strategy

This deployment uses heterogeneous memory rather than trying to place the complete model and runtime state in VRAM:

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

Current reference configuration:

```yaml
model:
  max_seq_len: 81920
  cache_size: 81920
  cache_mode: FP16

  cpu_moe_offload_layers: 999
  ngram_ram: false

memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

`sysmem_recurrent_cache` and `sysmem_kv_cache` are different controls. Benchmark them independently. Larger values are not guaranteed to be faster, and the best result can change with context length.

The API is intentionally bound to `127.0.0.1` with authentication disabled in the example configuration. **Do not expose an unauthenticated endpoint on `0.0.0.0` or a public network.**

---

## Recommended validation order

Do not debug the entire Agent stack at once:

```text
GPU / CUDA
    ↓
Torch
    ↓
ExLlamaV3
    ↓
TabbyAPI model loading
    ↓
/v1/models
    ↓
scripts/test_tool_call.py
    ↓
Hermes normal chat
    ↓
scripts/test_hermes_tool.ps1
    ↓
long-context benchmark
```

If `test_tool_call.py` passes but Hermes cannot execute tools, the model-serving layer is already working; focus on Hermes configuration and the Agent loop.

---

## Repository structure

```text
.
├── README.md
├── README.zh-CN.md
├── LICENSE
├── .gitignore
│
├── config/
│   └── config.example.yml
│
├── scripts/
│   ├── benchmark_chat.py
│   ├── test_tool_call.py
│   └── test_hermes_tool.ps1
│
├── benchmarks/
│   └── rtx5070-12gb.csv
│
└── docs/
    ├── installation.md
    ├── installation.zh-CN.md
    ├── benchmark.md
    ├── benchmark.zh-CN.md
    ├── tuning.md
    ├── tuning.zh-CN.md
    ├── troubleshooting.md
    └── troubleshooting.zh-CN.md
```

---

## Key lesson

**Model tool-calling capability, serving-layer tool-call support, and Agent tool execution are three separate requirements.**

```text
Model
→ generates the correct tool-call format

Serving backend
→ injects tool schemas and parses model output

Agent
→ executes the tool and returns the result to the model
```

---

## Upstream projects and credits

This repository is an integration/deployment recipe. It does not replace or relicense its upstream projects.

- Qwen3.8-Flash-Next — Qwen team
- Qwen3.8-Flash-Next EXL3 quantization — turboderp
- ExLlamaV3 — turboderp
- TabbyAPI — theroyallab
- Hermes Agent — Nous Research
- `flash-next-8gb` — lna-lab, whose heterogeneous-memory deployment work is useful background for this setup

Repository code/documentation are provided under the license in [`LICENSE`](LICENSE). Model weights and upstream software remain subject to their own licenses.

---

## Project scope

This repository focuses on a reproducible Windows + consumer NVIDIA GPU deployment path for Qwen3.8-Flash-Next EXL3 as a local Hermes Agent backend.

It documents a tested integration with particular emphasis on structured tool calling, heterogeneous memory, long-context operation and reproducible local benchmarking. Hardware requirements and optimal cache/offload settings vary between systems.
