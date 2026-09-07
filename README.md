# Qwen3.8-Flash-Next + Hermes Agent via ExLlamaV3 + TabbyAPI

**English** | [简体中文](README.zh-CN.md)

Run **Qwen3.8-Flash-Next EXL3** as a local agent backend for **Hermes Agent** using **ExLlamaV3 + TabbyAPI**, with native OpenAI-compatible tool calling on a consumer NVIDIA GPU（RTX 5070 VRAM 12G）.

This repository documents a tested Windows deployment path for turning a locally quantized Qwen3.8-Flash-Next model from a normal chat model into a functional local agent backend with structured `tool_calls`.

## Quick Start

The complete installation guide is available in:

[`docs/installation.md`](docs/installation.md)

The deployment process is:
```text
1. Prepare a Qwen3.8-Flash-Next EXL3 model
2. Install TabbyAPI + ExLlamaV3
3. Copy and edit config/config.example.yml
4. Start TabbyAPI
5. Verify structured tool calling
6. Connect Hermes Agent
7. Verify real tool execution
```
Once TabbyAPI is installed and configured, start the server with:

```powershell
cd E:\tabbyAPI
& ".\venv\Scripts\python.exe" .\main.py
```

Verify that the API is running:
```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

Then verify native structured tool calling:
```powershell
python scripts/test_tool_call.py
```

A successful result should contain:
```text
Finish reason: tool_calls
PASS: Structured tool calling works.
```

Finally, configure Hermes `hermes model` with:
```text
Provider:              Custom endpoint
API compatibility:     Chat Completions
Base URL:              http://127.0.0.1:8088/v1
Model:                 Qwen3.8-Flash-Next-exl3-3.05bpw
Context length:        81920
Maximum output tokens: 16384
```

For the full procedure, including Python/CUDA setup and the final Hermes file-tool integration test, see the installation guide.

---

## Documentation
### Installation
[`docs/installation.md`](docs/installation.md)

Complete Windows setup from:
```text
EXL3 model
→ ExLlamaV3
→ TabbyAPI
→ structured tool_calls
→ Hermes Agent
```
Use this if you are setting up the stack for the first time.

### Configuration
[`config/config.example.yml`](config/config.example.yml)

A tested TabbyAPI configuration for:
* 81,920-token context
* FP16 KV cache
* CPU MoE offloading
* disk-backed n-gram embeddings
* 2 GB system-memory second-tier KV cache
* `qwen3_coder` tool parsing

### Tool-call verification
[`scripts/test_tool_call.py`](scripts/test_tool_call.py)

Tests:
```text
OpenAI client
→ TabbyAPI
→ Qwen3.8-Flash-Next
→ qwen3_coder parser
→ structured OpenAI tool_calls
```

This deliberately bypasses Hermes so that the model-serving layer can be tested independently.

### Troubleshooting

[`docs/troubleshooting.md`](docs/troubleshooting.md)

Covers common problems including:
* localhost requests being routed through a proxy;
* `curl` working while Python fails;
* chat working but `tool_calls` remaining empty;
* `uv` installing into the wrong Python environment;
* large Torch wheel TLS failures;
* Hermes context / `max_tokens` conflicts;
* CPU MoE and KV-cache memory behavior.

---

## Recommended validation order
Do not debug the complete Agent stack at once.
Use this sequence:
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
Hermes real tool execution
```
If:
```text
test_tool_call.py = PASS
```
but Hermes still cannot execute tools, the model-serving layer is already working, and the remaining problem is likely in the Hermes configuration or Agent loop.


## Why this repository exists

Running a model through an OpenAI-compatible `/v1/chat/completions` endpoint does **not** automatically mean the server supports OpenAI-compatible tool calling.

A minimal inference server may successfully handle:

```text
messages
→ model
→ assistant content
```

while silently ignoring:

```text
tools
tool_choice
tool_calls
```

In our initial setup, Qwen3.8-Flash-Next could reason that a tool should be used, but Hermes reported:
```text
0 tool calls
```
The problem was not the model itself.
The missing layer was the serving stack.

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
## Tested setup
This repository documents a configuration tested on:

```text
OS:          Windows 11
CPU:         AMD Ryzen 9 9950X3D
GPU:         NVIDIA GPU with 12 GB VRAM
RAM:         96 GB
Model:       Qwen3.8-Flash-Next EXL3 3.05 bpw
Inference:   ExLlamaV3
API server:  TabbyAPI
Agent:       Hermes Agent
```
This is a **tested configuration**, not a statement of minimum hardware requirements.

## Memory strategy

The deployment uses heterogeneous memory rather than attempting to place the entire model in VRAM:

```text
GPU VRAM
├── GPU-resident model components
├── attention compute
├── active KV cache
└── runtime buffers

System RAM
├── CPU-offloaded MoE experts
└── second-tier KV cache

NVMe SSD
└── Qwen3.8-Flash-Next n-gram embedding table

```

Current tested configuration:

```yaml
max_seq_len: 81920
cache_size: 81920
cache_mode: FP16

cpu_moe_offload_layers: 999
ngram_ram: false

memory:
   sysmem_kv_cache: 2048

```

On the tested 12 GB GPU, static dedicated VRAM usage after model loading is approximately **10.5 GB**.

Actual memory consumption depends on the GPU driver, CUDA runtime, ExLlamaV3 version and model quantization.


## Repository structure
```text
.
├── README.md
├── LICENSE
├── .gitignore
├── config/
│   └── config.example.yml
├── scripts/
│   └── test_tool_call.py
└── docs/
    ├── installation.md
    └── troubleshooting.md

```
## Status
Currently validated:

\* Qwen3.8-Flash-Next EXL3 inference

\* 81,920-token context configuration

\* FP16 KV cache

\* CPU MoE expert offloading

\* system-memory second-tier KV cache

\* OpenAI-compatible `/v1/chat/completions`

\* structured OpenAI `tool_calls`

\* `qwen3_coder` tool-call parsing

\* Hermes Agent integration


## Key lesson

**Model tool-calling capability, serving-layer tool-call support, and agent tool execution are three different things.**

A model can know that it should call a tool while the serving backend still returns only ordinary text.

For a real agent loop, all three layers must work:

```text
Model
→ generates the correct tool-call format

Serving backend
→ injects tool schemas and parses model output

Agent
→ executes the tool and returns the result to the model

```



## Project scope

This repository focuses on a reproducible **Windows + consumer NVIDIA GPU** deployment path for Qwen3.8-Flash-Next EXL3 as a local Hermes Agent backend.

It is not a replacement for TabbyAPI, ExLlamaV3, Qwen or Hermes. It documents a tested integration of these projects, with particular emphasis on structured tool calling and low-VRAM heterogeneous inference.

Hardware requirements and optimal cache/offload settings will vary between systems.


