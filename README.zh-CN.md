# Qwen3.8-Flash-Next + Hermes Agent via TabbyAPI

[English](README.md) | **简体中文**

使用 **ExLlamaV3 + TabbyAPI**，把 **Qwen3.8-Flash-Next EXL3** 作为 **Hermes Agent** 的本地后端，并在消费级 NVIDIA GPU 上获得原生 OpenAI-compatible 结构化 tool calling。

本仓库记录的是一条已经实际跑通的 **Windows + 消费级 NVIDIA GPU** 部署路线。参考机器为 **RTX 5070 12 GB + 96 GB RAM**，模型为 **Qwen3.8-Flash-Next EXL3 3.05 bpw**。

> 本仓库中的配置是 **known-good reference**，不是全局最优参数。cache/offload 应该在你自己的硬件和目标 context length 上实测。

## 已验证内容

- Qwen3.8-Flash-Next EXL3 + ExLlamaV3 推理；
- TabbyAPI OpenAI-compatible `/v1/chat/completions`；
- 81,920-token context + FP16 primary KV cache；
- CPU MoE expert offload + NVMe-backed n-gram 数据；
- `tool_format: qwen3_coder` 结构化 OpenAI `tool_calls`；
- Hermes Agent 真实工具执行；
- 可复现的 32K / 64K 长上下文与 cache-reuse benchmark。

---

## 快速开始

完整安装文档：

[`docs/installation.zh-CN.md`](docs/installation.zh-CN.md)

部署流程：

```text
1. 准备 Qwen3.8-Flash-Next EXL3 模型
2. 安装 TabbyAPI + ExLlamaV3
3. 复制并修改 config/config.example.yml
4. 启动 TabbyAPI
5. 验证 structured tool calling
6. 接入 Hermes Agent
7. 验证 Hermes 真实执行工具
8. benchmark 自己的硬件
```

启动 TabbyAPI：

```powershell
cd E:\tabbyAPI
& ".\venv\Scripts\python.exe" .\main.py
```

验证 API：

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

验证结构化 tool calling。如果系统 Python 没有 OpenAI SDK，可直接使用 Hermes 的 Python：

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

成功时应看到：

```text
Finish reason: tool_calls
PASS: Structured tool calling works.
```

然后配置 Hermes：

```text
Provider:              Custom endpoint
API compatibility:     Chat Completions
Base URL:              http://127.0.0.1:8088/v1
Model:                 Qwen3.8-Flash-Next-exl3-3.05bpw
Context length:        81920
Maximum output tokens: 16384
```

最后做真实 Agent 工具测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_hermes_tool.ps1
# or
Unblock-File .\scripts\test_hermes_tool.ps1
```

---

## 文档

### 安装

[`docs/installation.zh-CN.md`](docs/installation.zh-CN.md)

完整 Windows 路线：

```text
EXL3 model
→ ExLlamaV3
→ TabbyAPI
→ structured tool_calls
→ Hermes Agent
```

### 配置

[`config/config.example.yml`](config/config.example.yml)

当前参考机器的 known-good memory 配置：

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

其他关键设置：

```text
81,920-token context
FP16 primary KV cache
CPU MoE offloading
NVMe-backed n-gram data
qwen3_coder tool parsing
```

### Benchmark

[`docs/benchmark.zh-CN.md`](docs/benchmark.zh-CN.md)

不仅展示本机数据，也告诉你如何测试**自己的 OpenAI-compatible 本地模型**：

- 8K / 16K / 32K / 64K prompt；
- first-pass TTFT；
- long-prompt ingestion；
- decode throughput；
- exact-prefix cache reuse；
- recurrent/KV system-memory cache 调优；
- 多次重复后报告 median。

参考机器原始测量：

[`benchmarks/rtx5070-12gb.csv`](benchmarks/rtx5070-12gb.csv)

### 性能调优

[`docs/tuning.zh-CN.md`](docs/tuning.zh-CN.md)

包括 MoE offload、FP16/Q8 KV、recurrent cache、second-tier KV cache、context、`cuda_malloc_async`，以及一次只改变一个变量的调参方法。

### Tool-call 验证

[`scripts/test_tool_call.py`](scripts/test_tool_call.py)

单独验证 serving layer：

```text
OpenAI client
→ TabbyAPI
→ Qwen3.8-Flash-Next
→ qwen3_coder parser
→ structured OpenAI tool_calls
```

[`scripts/test_hermes_tool.ps1`](scripts/test_hermes_tool.ps1) 再用随机 UUID 文件验证 Hermes 真的执行了 file tool，而不是猜测答案。

### 故障排查

[`docs/troubleshooting.zh-CN.md`](docs/troubleshooting.zh-CN.md)

包括 localhost proxy、Python/OpenAI SDK 环境、普通文本而非 `tool_calls`、Torch/CUDA 安装、context budget、RAM/VRAM、recurrent/KV cache 和 allocator/OOM 问题。

---

## Benchmark 摘要

参考机器：

```text
OS:          Windows 11
CPU:         AMD Ryzen 9 9950X3D
GPU:         NVIDIA GeForce RTX 5070 12 GB
RAM:         96 GB
Model:       Qwen3.8-Flash-Next EXL3 3.05 bpw
Context:     81,920
Primary KV:  FP16
```

当前 `10R / 4K / cudaMallocAsync=true` 实测：

| Prompt | First-pass TTFT | Cached-prefix TTFT | First-pass rate | Decode |
|---:|---:|---:|---:|---:|
| 32K | 33.248 s | 0.738 s | ~964 tok/s | ~21.1 tok/s |
| 64K | 65.743 s | 0.964 s | ~974 tok/s | ~20.4 tok/s |

在更广泛的 cache 实验中，64K 首次 long-prompt ingestion 大体在 **0.9–1.0K tok/s**；完全相同 prefix 的 TTFT 可从约 **65–70 s** 降到约 **0.5–1.8 s**，具体取决于 cache 配置和运行状态。

cached run 的 `prompt_tokens / TTFT` 不能当作真实物理 prefill throughput，只能理解成 effective cache-reuse rate。

---

## 为什么会有这个仓库？

有一个 OpenAI-compatible `/v1/chat/completions` endpoint，**并不代表** serving backend 一定支持 OpenAI-compatible tool calling。

一个最小 server 可能只处理：

```text
messages
→ model
→ assistant content
```

却忽略或错误处理：

```text
tools
tool_choice
tool_calls
```

我们最初就遇到过：模型知道应该调用工具，但 Hermes 仍然得到 0 tool calls。问题不在模型本身，而在 serving layer。

TabbyAPI 配合：

```yaml
tool_format: qwen3_coder
```

完整路径变成：

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

## 内存策略

这套方案使用异构内存，而不是试图把完整模型和全部 runtime state 都塞进 VRAM：

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

当前 reference：

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

`sysmem_recurrent_cache` 和 `sysmem_kv_cache` 是两个不同的控制项，应该分开 benchmark。更大并不保证更快，而且最佳结果可能随 context length 改变。

示例 API 绑定在 `127.0.0.1` 且关闭 authentication。**不要把无认证 endpoint 暴露到 `0.0.0.0` 或公网。**

---

## 推荐验证顺序

不要一次 debug 整个 Agent stack：

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

如果 `test_tool_call.py` PASS，但 Hermes 仍不能执行工具，那么 serving layer 已经工作，应重点检查 Hermes 配置和 Agent loop。

---

## 仓库结构

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

## 最重要的经验

**模型会不会 tool calling、serving backend 会不会返回结构化 tool call、Agent 会不会真正执行工具，是三个不同的问题。**

```text
Model
→ 生成正确的 tool-call format

Serving backend
→ 注入 tool schema 并解析模型输出

Agent
→ 执行工具并把结果返回给模型
```

---

## Upstream 与 Credits

本仓库是 integration/deployment recipe，不替代也不重新授权上游项目。

- Qwen3.8-Flash-Next — Qwen team
- Qwen3.8-Flash-Next EXL3 quantization — turboderp
- ExLlamaV3 — turboderp
- TabbyAPI — theroyallab
- Hermes Agent — Nous Research
- `flash-next-8gb` — lna-lab；其异构内存部署工作为本路线提供了有价值的背景参考

本仓库代码/文档使用 [`LICENSE`](LICENSE) 中的许可；模型权重和上游软件遵循各自许可。

---

## 项目范围

本仓库关注 Windows + 消费级 NVIDIA GPU 上，Qwen3.8-Flash-Next EXL3 作为 Hermes Agent 本地后端的一条可复现部署路线。

重点是 structured tool calling、heterogeneous memory、长上下文运行和可复现 benchmark。不同硬件上的最优 cache/offload 参数会不同。



## 许可证

本仓库中原创的代码和文档采用 [MIT License](LICENSE)。

本项目依赖或集成的第三方软件及模型权重仍分别受其原许可证约束：

- Qwen3.8-Flash-Next 及其 EXL3 量化权重：
  Qwen Community License 1.0
- TabbyAPI：
  GNU Affero General Public License v3.0 (AGPL-3.0)
- ExLlamaV3：
  MIT License
- Hermes Agent：
  MIT License

本仓库的 MIT License 不会替代或修改上述第三方项目和模型权重的许可证。
