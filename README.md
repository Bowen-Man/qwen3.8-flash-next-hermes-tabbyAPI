# Qwen3.8-Flash-Next + Hermes Agent via TabbyAPI

Run **Qwen3.8-Flash-Next EXL3** as a local agent backend for **Hermes Agent** using **ExLlamaV3 + TabbyAPI**, with native OpenAI-compatible tool calling on a consumer NVIDIA GPU.

This repository documents a tested Windows deployment path for turning a locally quantized Qwen3.8-Flash-Next model from a normal chat model into a functional local agent backend with structured `tool_calls`.

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
├── .gitignore
├── config/
│   └── config.example.yml
├── scripts/
│   └── test_tool_call.py
└── docs/
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

\* structured OpenAI `tool\_calls`

\* `qwen3\_coder` tool-call parsing

\* Hermes Agent integration


## Key lesson

\*\*Model tool-calling capability, serving-layer tool-call support, and agent tool execution are three different things.\*\*

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

## Next

Detailed installation instructions, configuration, tool-call verification and troubleshooting will be added to this repository.



