# Benchmark Log

Use this file to record reproducible performance measurements.

## Hardware

```text
OS:
CPU:
GPU:
VRAM:
RAM:
Storage:
NVIDIA driver:
```

## Software

```text
Model:
Quantization:
TabbyAPI:
ExLlamaV3:
Python:
Torch:
CUDA:
Hermes:
```

## Baseline configuration

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

## Results

| Run | Changed parameter | Static VRAM | RAM used | Prompt size | TTFT | Prefill tok/s | Decode tok/s | Tool call | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | Baseline | | | | | | | ✅ | |
| 2 | | | | | | | | | |
| 3 | | | | | | | | | |

## Method

Change only one parameter at a time.

Keep constant:

- model and quantization;
- prompt;
- generation settings;
- background applications;
- Hermes / TabbyAPI versions where possible.

For tool-call testing, use `scripts/test_tool_call.py`.
