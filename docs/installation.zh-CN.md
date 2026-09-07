# 安装指南

[English](installation.md) | **简体中文**

本文档介绍如何在 Windows 上完整部署：

```text
Qwen3.8-Flash-Next EXL3
        ↓
ExLlamaV3
        ↓
TabbyAPI
        ↓
OpenAI Chat Completions + structured tool_calls
        ↓
Hermes Agent
```

目标不只是让模型“能生成文本”。

真正的最终成功标准是：

```text
Hermes 发送工具定义
        ↓
Qwen 选择要调用的工具
        ↓
TabbyAPI 返回结构化 OpenAI tool_calls
        ↓
Hermes 真正执行工具
        ↓
工具结果返回给 Qwen
        ↓
Qwen 基于工具结果生成最终回答
```

---

# 1. 已验证环境

以下配置已经实际跑通：

| 组件 | 已验证配置 |
|---|---|
| OS | Windows 11 |
| CPU | AMD Ryzen 9 9950X3D |
| GPU | NVIDIA GPU，12 GB VRAM |
| 系统内存 | 96 GB |
| TabbyAPI Python | Python 3.12.13 |
| Torch | 2.9.0+cu128 |
| ExLlamaV3 | 1.4.8 |
| 模型 | Qwen3.8-Flash-Next EXL3 3.05 bpw |
| Context | 81,920 tokens |
| KV cache | FP16 |
| 系统内存 cache | 10 GB recurrent + 4 GB second-tier KV |
| Agent | Hermes Agent |
| API 模式 | OpenAI Chat Completions |

这是一套**已经验证成功的配置**，并不代表最低硬件要求。

不同 GPU、不同量化版本以及不同 RAM / VRAM 条件下，cache 和 offload 参数都可能需要调整。

---

# 2. 开始前需要准备什么

你需要：

- Windows 10/11；
- NVIDIA GPU；
- 较新的 NVIDIA 驱动；
- Git；
- Python 3.12；
- 足够的系统内存用于 CPU MoE offloading；
- Qwen3.8-Flash-Next EXL3 模型；
- Hermes Agent；
- TabbyAPI。

本文默认使用 CUDA 12.x 环境。

对于本仓库这套已验证配置，建议使用 Python 3.12。

检查 Python：

```powershell
py -3.12 --version
```

预期：

```text
Python 3.12.x
```

检查 GPU：

```powershell
nvidia-smi
```

---

# 3. 准备 EXL3 模型

本文使用：

```text
Qwen3.8-Flash-Next-exl3-3.05bpw
```

参考 EXL3 权重来自 [turboderp/Qwen3.8-Flash-Next-exl3](https://huggingface.co/turboderp/Qwen3.8-Flash-Next-exl3)。该模型页目前注明这些 quant 需要 **ExLlamaV3 v1.4.5 或更新版本**；本文参考机器使用 ExLlamaV3 1.4.8。

模型可以放在任意位置。

例如：

```text
E:\flash-next\
└── Qwen3.8-Flash-Next-exl3-3.05bpw\
```

需要理解：

```text
model_dir
    ↓
E:\flash-next

model_name
    ↓
Qwen3.8-Flash-Next-exl3-3.05bpw
```

不要把 `model_dir` 和 `model_name` 都填写成完整模型路径。

---

# 4. 安装 TabbyAPI

从 GitHub 克隆官方 `theroyallab/tabbyAPI` 仓库。

例如将安装目录设为：

```text
E:\tabbyAPI
```

最终目录大致应为：

```text
E:\tabbyAPI\
├── main.py
├── start.bat
├── config_sample.yml
├── pyproject.toml
└── ...
```

---

# 5. 安装推理环境

## Windows 推荐方式

打开 PowerShell：

```powershell
cd E:\tabbyAPI
.\start.bat
```

第一次运行时，TabbyAPI 会创建自己的虚拟环境，并安装所需推理依赖。

如果要求选择 CUDA 版本，请选择 CUDA 12.x。

虚拟环境通常位于：

```text
E:\tabbyAPI\venv
```

验证：

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" --version
```

本仓库测试时使用：

```text
Python 3.12.13
```

> 如果 `start.bat` 在下载大型 Torch wheel 时反复失败，不要无限重试。请直接跳到本文第 7 节，或查看 [`troubleshooting.zh-CN.md`](troubleshooting.zh-CN.md)。

---

# 6. 验证 Torch 和 CUDA

安装完成后运行：

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" -c `
"import torch; print('Torch:', torch.__version__); print('CUDA:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```

本次已验证环境输出大致为：

```text
Torch: 2.9.0+cu128
CUDA: 12.8
CUDA available: True
GPU: NVIDIA ...
```

随后验证 ExLlamaV3：

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" -c `
"import torch, exllamav3; print('Torch:', torch.__version__); print('ExLlamaV3: OK')"
```

预期：

```text
ExLlamaV3: OK
```

---

# 7. 如果大型 Torch wheel 一直下载失败

CUDA 版 Torch wheel 往往有数 GB。

在网络不稳定、VPN / 代理链复杂或者 Windows TLS 环境异常时，安装可能报：

```text
peer closed connection
```

或者：

```text
missing close_notify
```

这时不要不断从头重装整个环境。

更稳妥的策略是：

```text
单独下载 wheel，并启用断点续传
        ↓
检查文件是否完整
        ↓
从本地 wheel 安装
```

详细命令见：

[`troubleshooting.zh-CN.md`](troubleshooting.zh-CN.md)

其中包含我们实际使用过的 `curl.exe -C -` 断点续传方案。

---

# 8. 创建 `config.yml`

TabbyAPI 自带：

```text
config_sample.yml
```

创建：

```text
E:\tabbyAPI\config.yml
```

你可以直接复制本仓库：

```text
config/config.example.yml
```

然后修改模型路径。

已验证配置：

```yaml
network:
  host: 127.0.0.1
  port: 8088
  disable_auth: true
  api_servers: ["OAI"]

model:
  model_dir: E:\flash-next
  model_name: Qwen3.8-Flash-Next-exl3-3.05bpw

  backend: exllamav3

  max_seq_len: 81920
  cache_size: 81920
  cache_mode: FP16

  cpu_moe_offload_layers: 999
  ngram_ram: false

  chunk_size: 2048
  output_chunking: true
  max_batch_size: 1

  reasoning: true
  start_in_reasoning: auto
  tool_calls_in_reasoning: true

  tool_format: qwen3_coder

sampling:
  override_preset: safe_defaults

memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

---

# 9. 理解几个重要参数

## Context

```yaml
max_seq_len: 81920
cache_size: 81920
```

本次测试配置提供 81,920 token 上下文。

`cache_size` 必须足以支撑配置的 sequence length。

---

## KV cache

```yaml
cache_mode: FP16
```

本次测试保持主 KV cache 为 FP16。

如果显存更少，可以考虑 TabbyAPI / ExLlamaV3 支持的量化 KV cache，但那已经属于进一步调优，不是本教程的默认配置。

---

## CPU MoE offloading

```yaml
cpu_moe_offload_layers: 999
```

Qwen3.8-Flash-Next 是 MoE 模型。

将该值设为很大的数，例如：

```text
999
```

会让所有符合条件的 MoE 层进行 CPU offload。

这是该模型能够在较小消费级 GPU 上运行的关键原因之一。

启动时日志会出现大量类似：

```text
CPU-offloaded experts (worker):
model.language_model.layers.X.mlp
```

这是预期行为，不是报错。

---

# 10. Qwen n-gram 存储

```yaml
ngram_ram: false
```

Qwen3.8-Flash-Next 使用 n-gram embedding table。

当：

```yaml
ngram_ram: false
```

时，这张表不会被完整加载进系统 RAM，而会保留在存储侧并在推理过程中读取。

这样可以降低 RAM 占用，但会增加对存储性能的依赖。

建议使用较快的 SSD / NVMe。

---

# 11. 系统内存 recurrent 与 KV cache

当前 known-good reference：

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

`sysmem_recurrent_cache` 与 `sysmem_kv_cache` 是两个不同的控制项，不能简单理解为“把多少 GB active GPU cache 永久搬进 RAM”。

参考机器会主动使用大量 system RAM 做异构推理。cache 效果与 workload/context length 有关，分配更大不保证更快。

`cuda_malloc_async: true` 是当前 known-good reference 的一部分。在本机 10R/4K 64K workload 下，打开后 TTFT/decode 与之前 `false` 的两次运行处于同一性能区间。如果出现 intermittent CUDA OOM 或 allocator instability，再固定其他参数、单独测试 `false`。

调参方法和实测数据见：

```text
docs/tuning.zh-CN.md
docs/benchmark.zh-CN.md
```

# 12. 最关键的 Agent 参数

这一行非常重要：

```yaml
tool_format: qwen3_coder
```

如果没有兼容的 tool parser，模型可能正常聊天，甚至 reasoning 中知道“应该调用工具”，但 Agent 仍然拿不到结构化 tool call。

要区分：

```text
模型普通文本：
"I should call read_file"
```

和：

```text
OpenAI API：
finish_reason = tool_calls
tool_calls = [...]
```

Hermes 真正需要的是第二种。

模型“嘴上说要调用工具”并不等于 tool calling 已经打通。

---

# 13. 启动 TabbyAPI

环境安装完成以后，日常启动建议直接运行：

```powershell
cd E:\tabbyAPI

& ".\venv\Scripts\python.exe" .\main.py
```

这条命令的实际含义是：

```text
E:\tabbyAPI\venv\Scripts\python.exe
                ↓
              执行
                ↓
E:\tabbyAPI\main.py
```

也就是说，我们明确指定 TabbyAPI 自己的 Python 环境运行 `main.py`。

日常使用时不必反复运行安装脚本。

使用模型期间请保持这个 PowerShell 窗口开启。

---

# 14. 确认模型加载成功

预期日志首先会包含：

```text
CPU-offloaded experts (worker): ...
```

随后：

```text
Model loaded in ...
```

以及：

```text
Serving OAI API on 127.0.0.1:8088
```

状态行应类似：

```text
cache 0/81,920 tokens in use
```

此时：

```text
TabbyAPI
    ↓
ExLlamaV3
    ↓
Qwen3.8-Flash-Next
```

已经运行起来。

注意：**到这里 Hermes 还没有参与。**

---

# 15. 验证 API Server

另开一个 PowerShell：

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

应当能看到：

```text
Qwen3.8-Flash-Next-exl3-3.05bpw
```

后面配置 Hermes 时，请使用这个真实模型 ID。

如果 `/v1/models` 同时列出一些奇怪的目录名，不要默认它们都是真模型。具体原因见故障排查文档。

---

# 16. 配置 Hermes 之前先验证结构化 tool calling

本仓库提供：

```text
scripts/test_tool_call.py
```

这个脚本会**刻意绕过 Hermes**。

它只验证：

```text
OpenAI client
    ↓
TabbyAPI
    ↓
Qwen
    ↓
qwen3_coder parser
    ↓
structured tool_calls
```

这是非常重要的分层测试。

因为如果这一层都失败，就没有必要先去调 Hermes。

---

# 17. 准备一个小型测试环境

进入本仓库：

```powershell
cd E:\GitHub\qwen3.8-flash-next-hermes-tabbyAPI

py -3.12 -m venv venv

& ".\venv\Scripts\python.exe" -m pip install openai
```

然后运行：

```powershell
& ".\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

如果你已经安装 Hermes，也可以直接使用 Hermes 自带且已经包含 OpenAI SDK 的 Python 环境运行这个测试脚本，详见故障排查文档。

---

# 18. Tool-call 测试的预期结果

成功输出应类似：

```text
Model: Qwen3.8-Flash-Next-exl3-3.05bpw
Finish reason: tool_calls

Content: None

PASS: Structured tool calling works.
Tool name: get_time
Arguments: {}
```

真正关键的是：

```text
finish_reason = tool_calls
```

以及：

```text
tool_calls != None
```

下面这种输出**不算成功**：

```text
I should call get_time...
```

因为那只是普通文本。

如果脚本输出：

```text
PASS: Structured tool calling works.
```

说明：

```text
Qwen + TabbyAPI + qwen3_coder parser
```

这一层已经具备作为 Agent backend 的基本条件。

---

# 19. 安装 Hermes Agent

按照 Hermes 当前官方 Windows 安装方式安装 Hermes Agent。

安装后打开新的 PowerShell：

```powershell
hermes --version
```

再检查：

```powershell
hermes doctor
```

如果核心安装项有错误，应先处理这些问题。

各种可选云 provider、Discord 等集成，并不是连接本地 TabbyAPI 模型的必要条件。

---

# 20. 配置 Hermes

运行：

```powershell
hermes model
```

Provider 选择：

```text
Custom endpoint
```

API compatibility 选择：

```text
Chat Completions
```

填写：

```text
Base URL:
http://127.0.0.1:8088/v1

Model:
Qwen3.8-Flash-Next-exl3-3.05bpw

API key:
local
```

因为示例 TabbyAPI 配置使用：

```yaml
disable_auth: true
```

所以本地情况下 API key 并不会被实际校验。

填：

```text
local
```

作为占位值即可。

> 不要把 `disable_auth: true` 的服务暴露给不可信网络。本仓库默认只监听 `127.0.0.1`。

---

# 21. 配置 Hermes 上下文

Hermes 询问 context length 时填写：

```text
81920
```

当前 Hermes 对本地 Agent 模型要求至少 **64K context window**。本文使用的 81,920-token server 配置满足这一要求，同时给 system prompt、tool schema、history 和 tool results 留出足够空间。

然后显式设置最大输出：

```powershell
hermes config set model.context_length 81920
hermes config set model.max_tokens 16384
```

验证：

```powershell
hermes config get model.context_length
hermes config get model.max_tokens
```

预期：

```text
81920
16384
```

于是大致形成：

```text
81,920 total context
│
├── ~65,536 用于：
│      system prompt
│      conversation history
│      tool schemas
│      tool results
│
└── 最多 16,384 output tokens
```

这样可以避免客户端把整个 context window 都当成输出预算，导致 prompt + output 总预算超限。

---

# 22. 先验证 Hermes 普通聊天

在测试工具之前：

```powershell
hermes chat --oneshot --toolsets clarify `
  -q "What model are we using?"
```

如果模型能正常回答，说明：

```text
Hermes
    ↓
TabbyAPI
    ↓
Qwen
```

基础聊天链已经通了。

普通聊天都没有跑通时，不要先调试 Agent tools。

---

# 23. 做一次真正的 Agent integration test

`test_tool_call.py` 能证明 structured tool call 已存在。

但它还不能证明：

> Hermes 真的执行了那个工具。

因此最终验收需要一个 Hermes 自己执行工具的测试。

先创建一个包含随机 UUID 的文件：

```powershell
$token = [guid]::NewGuid().ToString()

Set-Content "$env:TEMP\hermes_tool_test.txt" $token

$token
```

随机 UUID 的意义是：

> 模型事先不可能知道文件内容，因此不能靠猜测蒙对。

---

# 24. 让 Hermes 读取这个文件

运行：

```powershell
hermes chat --oneshot --toolsets file `
  -q "You must use the file tool to read C:\Users\Administrator\AppData\Local\Temp\hermes_tool_test.txt and return its contents exactly. Do not guess."
```

成功的 Agent loop 应该：

1. 生成结构化 `read_file` tool call；
2. Hermes 真正执行这个工具；
3. 返回随机 UUID；
4. 会话统计中至少出现一次真实 tool call。

完整成功路径：

```text
Hermes
    ↓
tools=[read_file,...]
    ↓
TabbyAPI
    ↓
Qwen
    ↓
qwen3_coder tool call
    ↓
TabbyAPI
    ↓
OpenAI tool_calls
    ↓
Hermes
    ↓
read_file executes
    ↓
tool result
    ↓
Qwen
    ↓
final answer
```

到这里，这套部署才真正成为一个可用的本地 Agent backend。

---

# 25. 日常如何启动

全部安装完成以后，平时只需要启动模型服务器：

```powershell
cd E:\tabbyAPI

& ".\venv\Scripts\python.exe" .\main.py
```

等待：

```text
Model loaded
```

和：

```text
Serving OAI API on 127.0.0.1:8088
```

出现。

保持该终端窗口开启。

然后另开一个终端：

```powershell
hermes
```

如果关闭 TabbyAPI 的终端：

```text
Python process stops
        ↓
model unloads
        ↓
port 8088 closes
        ↓
Hermes 无法再连接本地模型
```

---

# 26. 推荐的验证顺序

每次重装或修改重要配置后，建议按下面顺序验证：

```text
1. GPU 能被系统识别
        ↓
2. Torch + CUDA 正常
        ↓
3. ExLlamaV3 能 import
        ↓
4. TabbyAPI 能加载模型
        ↓
5. /v1/models 正常
        ↓
6. test_tool_call.py PASS
        ↓
7. Hermes 普通聊天正常
        ↓
8. Hermes 真实 file-tool 测试正常
```

不要把所有层同时混在一起 debug。

---

# 27. 每个组件到底负责什么

理解这些层次，会让排障简单很多。

```text
Hermes Agent
│
│  Agent orchestration
│  工具执行
│  对话循环
│
▼
TabbyAPI
│
│  OpenAI-compatible API server
│  chat template
│  工具 schema 处理
│  qwen3_coder parser
│
▼
ExLlamaV3
│
│  inference engine
│  GPU 执行
│  CPU MoE offloading
│  cache 管理
│
▼
Qwen3.8-Flash-Next EXL3
│
│  模型权重
│  reasoning
│  工具选择能力
│
▼
GPU + CPU + RAM + SSD
```

某一层失败，不等于模型本身坏了。

---

# 28. 已验证的内存架构

当前 12 GB reference 大致采用：

```text
GPU VRAM
├── GPU-resident model components
├── attention compute
├── active / primary FP16 KV state
└── runtime buffers

System RAM
├── CPU-offloaded MoE experts
├── recurrent cache
├── second-tier KV cache
└── runtime / OS memory

NVMe SSD
└── n-gram embedding data
```

当前 reference memory：

```yaml
memory:
  sysmem_recurrent_cache: 10240
  sysmem_kv_cache: 4096
  sysmem_multimodal_cache: 1024
  cuda_malloc_async: true
```

因此它更准确的描述是**异构推理（heterogeneous inference）**，而不是“把巨大模型完全塞进 12 GB 显卡”。

# 29. 如果出现问题

请查看：

[`troubleshooting.zh-CN.md`](troubleshooting.zh-CN.md)

其中包括：

- localhost 被代理劫持；
- `APIConnectionError`；
- `curl` 正常但 Python 失败；
- 模型只输出普通文本而没有 `tool_calls`；
- `uv` 装进错误 Python 环境；
- Torch 大 wheel TLS 失败；
- context / `max_tokens` 冲突；
- `/v1/models` 出现奇怪目录；
- RAM / VRAM 行为；
- 二级 KV cache 行为。

---

# 30. 最终成功清单

以下项目全部满足，才算安装完整：

```text
[ ] TabbyAPI 成功加载 EXL3 模型

[ ] CUDA available = True

[ ] /v1/models 返回真实模型 ID

[ ] scripts/test_tool_call.py 输出 PASS

[ ] finish_reason = tool_calls

[ ] Hermes 普通聊天正常

[ ] Hermes 能真正执行 file tool

[ ] Hermes 能返回从磁盘读取的不可预测随机 UUID
```

全部通过后，完整本地 Agent stack 已经工作：

```text
Qwen3.8-Flash-Next
+
ExLlamaV3
+
TabbyAPI
+
OpenAI structured tool calling
+
Hermes Agent
```
