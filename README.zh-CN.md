# Qwen3.8-Flash-Next + Hermes Agent via TabbyAPI

[English](README.md) | **简体中文**

使用 **ExLlamaV3 + TabbyAPI**，在消费级 NVIDIA GPU 上将 **Qwen3.8-Flash-Next EXL3** 作为 **Hermes Agent** 的本地推理后端，并支持原生 OpenAI 兼容的结构化工具调用（`tool_calls`）。

本仓库记录了一条经过实际验证的 Windows 部署路径：把本地量化的 Qwen3.8-Flash-Next 从“能正常聊天的本地模型”，进一步接成一个能够向 Hermes Agent 返回结构化 `tool_calls` 的本地 Agent 后端。

## 快速开始

完整安装指南：

[`docs/installation.zh-CN.md`](docs/installation.zh-CN.md)

整体部署流程：

```text
1. 准备 Qwen3.8-Flash-Next EXL3 模型
2. 安装 TabbyAPI + ExLlamaV3
3. 复制并修改 config/config.example.yml
4. 启动 TabbyAPI
5. 验证结构化 tool calling
6. 连接 Hermes Agent
7. 验证真实工具执行
```

TabbyAPI 安装和配置完成后，启动服务：

```powershell
cd E:\tabbyAPI
& ".\venv\Scripts\python.exe" .\main.py
```

验证 API 是否已经启动：

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

然后验证原生结构化工具调用：

```powershell
python scripts/test_tool_call.py
```

成功时应看到类似：

```text
Finish reason: tool_calls
PASS: Structured tool calling works.
```

最后，在 Hermes 中配置：

```text
Provider:              Custom endpoint
API compatibility:     Chat Completions
Base URL:              http://127.0.0.1:8088/v1
Model:                 Qwen3.8-Flash-Next-exl3-3.05bpw
Context length:        81920
Maximum output tokens: 16384
```

包括 Python/CUDA 环境、TabbyAPI 配置以及最终 Hermes 文件工具集成测试在内的完整流程，请参阅安装指南。

---

## 文档

### 安装

[`docs/installation.zh-CN.md`](docs/installation.zh-CN.md)

完整的 Windows 部署链路：

```text
EXL3 模型
→ ExLlamaV3
→ TabbyAPI
→ structured tool_calls
→ Hermes Agent
```

如果你是第一次搭建整套环境，从这里开始。

### 配置

[`config/config.example.yml`](config/config.example.yml)

当前经过实测的一套 TabbyAPI 配置包括：

- 81,920 token 上下文；
- FP16 KV cache；
- CPU MoE offloading；
- 基于磁盘读取的 n-gram embeddings；
- 2 GB 系统内存二级 KV cache；
- `qwen3_coder` 工具调用解析。

### Tool-call 验证

[`scripts/test_tool_call.py`](scripts/test_tool_call.py)

该脚本验证：

```text
OpenAI client
→ TabbyAPI
→ Qwen3.8-Flash-Next
→ qwen3_coder parser
→ structured OpenAI tool_calls
```

它会**刻意绕过 Hermes**，从而可以独立判断“模型 + serving backend + tool parser”这一层是否已经正常工作。

### 故障排查

[`docs/troubleshooting.zh-CN.md`](docs/troubleshooting.zh-CN.md)

目前记录的常见问题包括：

- localhost 请求被系统代理劫持；
- `curl` 正常但 Python 请求失败；
- 普通聊天正常，但 `tool_calls` 为空；
- `uv` 把依赖安装进错误的 Python 环境；
- 大体积 Torch wheel 下载时 TLS 中断；
- Hermes context / `max_tokens` 冲突；
- CPU MoE 与 KV cache 的 RAM / VRAM 行为。

---

## 推荐的验证顺序

不要一上来同时调试整个 Agent 链。

建议按下面顺序逐层验证：

```text
GPU / CUDA
    ↓
Torch
    ↓
ExLlamaV3
    ↓
TabbyAPI 模型加载
    ↓
/v1/models
    ↓
scripts/test_tool_call.py
    ↓
Hermes 普通聊天
    ↓
Hermes 真实工具执行
```

如果：

```text
test_tool_call.py = PASS
```

但 Hermes 仍然无法真正执行工具，那么说明模型 serving 层已经基本正常，剩余问题更可能出在 Hermes 配置或 Agent loop。

## 为什么会有这个仓库？

模型可以通过 OpenAI-compatible 的 `/v1/chat/completions` 正常聊天，**并不等于**这个 server 已经支持 OpenAI-compatible tool calling。

一个最小化推理服务器可能正确处理：

```text
messages
→ model
→ assistant content
```

却忽略：

```text
tools
tool_choice
tool_calls
```

在我们最初的部署里，Qwen3.8-Flash-Next 在 reasoning 中已经能够判断“这里应该调用工具”，但 Hermes 最终显示：

```text
0 tool calls
```

问题并不在模型本身。

缺失的是中间的 serving / protocol 层。

使用 TabbyAPI，并配置：

```yaml
tool_format: qwen3_coder
```

之后，完整链路变成：

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
Hermes 执行工具
```

## 已验证环境

本仓库中的配置已经在以下环境中实际跑通：

```text
OS:          Windows 11
CPU:         AMD Ryzen 9 9950X3D
GPU:         NVIDIA GPU，12 GB VRAM
RAM:         96 GB
Model:       Qwen3.8-Flash-Next EXL3 3.05 bpw
Inference:   ExLlamaV3
API server:  TabbyAPI
Agent:       Hermes Agent
```

这是一个**经过验证的配置**，并不代表最低硬件要求。

## 内存策略

这套部署使用的是异构内存，而不是试图把完整模型全部塞进显存：

```text
GPU VRAM
├── GPU 常驻模型组件
├── attention compute
├── active KV cache
└── runtime buffers

System RAM
├── CPU-offloaded MoE experts
└── second-tier KV cache

NVMe SSD
└── Qwen3.8-Flash-Next n-gram embedding table
```

当前实测配置：

```yaml
max_seq_len: 81920
cache_size: 81920
cache_mode: FP16

cpu_moe_offload_layers: 999
ngram_ram: false

memory:
   sysmem_kv_cache: 2048
```

在本次测试使用的 12 GB GPU 上，模型加载完成后的 dedicated GPU memory 静态占用约为 **10.5 GB**。

实际内存和显存占用会受到 GPU 驱动、CUDA runtime、ExLlamaV3 版本以及模型量化方式等因素影响。

## 仓库结构

```text
.
├── README.md
├── README.zh-CN.md
├── LICENSE
├── .gitignore
├── config/
│   └── config.example.yml
├── scripts/
│   └── test_tool_call.py
└── docs/
    ├── installation.md
    ├── installation.zh-CN.md
    ├── troubleshooting.md
    └── troubleshooting.zh-CN.md
```

## 当前状态

目前已经验证：

- Qwen3.8-Flash-Next EXL3 推理；
- 81,920 token 上下文；
- FP16 KV cache；
- CPU MoE expert offloading；
- 系统内存二级 KV cache；
- OpenAI-compatible `/v1/chat/completions`；
- 结构化 OpenAI `tool_calls`；
- `qwen3_coder` tool-call parsing；
- Hermes Agent 集成。

## 最重要的经验

**模型具备工具调用能力、serving 层支持结构化 tool calling、Agent 能够真正执行工具，是三件不同的事情。**

模型完全可能知道“这里应该调用某个工具”，但 serving backend 最终仍然只返回普通文本。

一个真正可用的 Agent loop，至少需要三层全部打通：

```text
Model
→ 生成正确的 tool-call 格式

Serving backend
→ 注入工具 schema，并解析模型输出

Agent
→ 真正执行工具，并把结果返回给模型
```

## 项目范围

本仓库聚焦于一条可复现的 **Windows + 消费级 NVIDIA GPU** 部署路径：使用 Qwen3.8-Flash-Next EXL3 作为 Hermes Agent 的本地推理后端。

本仓库不是 TabbyAPI、ExLlamaV3、Qwen 或 Hermes 的替代品，而是记录这些项目如何在一个实际环境中组合使用，重点关注：

- 结构化工具调用；
- OpenAI-compatible Agent protocol；
- 低显存条件下的异构推理。

不同硬件上的最低要求和最优 cache / offload 参数可能不同。
