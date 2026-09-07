# 故障排查

[English](troubleshooting.md) | **简体中文**

本文汇总在 Windows 上运行：

**Qwen3.8-Flash-Next EXL3 + ExLlamaV3 + TabbyAPI + Hermes Agent**

过程中实际遇到的主要问题。

最重要的排障原则只有一句：

> **不要一次调试整个 Agent stack。**

应该逐层测试：

```text
Model files
    ↓
ExLlamaV3 model loading
    ↓
TabbyAPI server
    ↓
/v1/models
    ↓
/v1/chat/completions
    ↓
structured tool_calls
    ↓
Hermes Agent
    ↓
actual tool execution
```

---

# 1. Hermes 报 `APIConnectionError`

## 症状

Hermes 报：

```text
APIConnectionError
```

但 TabbyAPI 或其他本地 server 看起来明明已经正常启动。

甚至：

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

还能正常工作。

## 可能原因：localhost 流量被系统代理劫持

Windows 上使用 VPN、Clash / Mihomo、V2Ray 等代理软件时，系统可能配置类似：

```text
127.0.0.1:7897
```

的 HTTP / HTTPS proxy。

Python 的 HTTP client（例如 `httpx`）可能自动继承这些环境设置。

于是原本应该：

```text
Hermes
    ↓
127.0.0.1:8088
```

的请求，实际上变成：

```text
Hermes
    ↓
httpx
    ↓
system proxy
    ↓
127.0.0.1:8088
```

本地请求被错误送进代理链。

## 检查

运行：

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  -c "import urllib.request; print(urllib.request.getproxies())"
```

如果看到系统代理，可以先临时设置：

```powershell
$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"
```

再测试 Hermes。

## 永久设置

```powershell
[Environment]::SetEnvironmentVariable(
    "NO_PROXY",
    "127.0.0.1,localhost",
    "User"
)

[Environment]::SetEnvironmentVariable(
    "no_proxy",
    "127.0.0.1,localhost",
    "User"
)
```

设置后重新打开终端。

---

# 2. `curl` 正常，但 Python / OpenAI SDK 失败

## 症状

下面这条正常：

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

但 Python 或 Hermes 失败。

## 原因

不同 HTTP client 对系统代理、环境变量、TLS 的处理方式可能不同。

`curl` 成功只证明：

```text
TabbyAPI 可以从某条网络路径访问
```

不一定证明：

```text
Python httpx / OpenAI SDK 使用的是同一条路径
```

## 用真正的 Hermes Python 测试

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  -c "import httpx; r=httpx.get('http://127.0.0.1:8088/v1/models'); print(r.status_code); print(r.text)"
```

必要时和禁用环境代理的版本比较：

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  -c "import httpx; c=httpx.Client(trust_env=False); r=c.get('http://127.0.0.1:8088/v1/models'); print(r.status_code); print(r.text)"
```

如果：

```text
trust_env=False
```

可以，而默认版本失败，那么系统代理继承基本就是主要嫌疑。

---

# 3. 普通聊天正常，但 tool calling 不工作

## 症状

普通对话完全正常。

模型甚至可能在 reasoning 里写：

```text
I should call read_file...
```

但是 Hermes 最终显示：

```text
0 tool calls
```

或者 API 返回：

```text
tool_calls=None
```

## 关键区别

下面两句话不是一回事：

```text
OpenAI-compatible chat server
```

和：

```text
OpenAI-compatible tool-calling server
```

一个最小化 `/v1/chat/completions` server 可能只支持：

```text
messages
→ model
→ content
```

但根本没有正确处理：

```text
tools
tool_choice
tool_calls
```

## 我们原先发生了什么

原来的轻量 `serve.py` 可以正常提供 Chat Completions，但没有完整实现 Hermes 所需要的结构化 tool-calling pipeline。

结果是：

```text
Hermes 发送 messages + tools
        ↓
server 主要处理 messages
        ↓
工具 schema 没被正确注入/解析
        ↓
模型可能用普通文字说“我要调用工具”
        ↓
server 仍返回普通 content
        ↓
Hermes 收不到 structured tool_calls
```

## 修复

使用 TabbyAPI，并配置：

```yaml
model:
  tool_format: qwen3_coder
```

以及：

```yaml
model:
  tool_calls_in_reasoning: true
```

对于 Qwen3.8-Flash-Next，`qwen3_coder` parser 会把模型生成的工具调用格式解析成 OpenAI-compatible structured `tool_calls`。

---

# 4. 如何绕过 Hermes 独立验证 tool calling

不要一上来就测整个 Hermes。

运行：

```powershell
python scripts/test_tool_call.py
```

或者明确使用一个已经装有 OpenAI SDK 的 Python：

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

预期：

```text
Finish reason: tool_calls

PASS: Structured tool calling works.
Tool name: get_time
Arguments: {}
```

真正关键的是：

```text
finish_reason='tool_calls'
```

以及：

```text
tool_calls=[...]
```

下面这种：

```text
I should call get_time...
```

**不算成功。**

那只是普通文本，并不是结构化 tool call。

## 如何解释结果

```text
test_tool_call.py PASS
+ Hermes tools PASS
→ 整条链路工作
```

```text
test_tool_call.py PASS
+ Hermes tools FAIL
→ 优先检查 Hermes 配置 / Agent loop
```

```text
test_tool_call.py FAIL
→ 优先检查 TabbyAPI / 模型 / tool parser
```

---

# 5. Hermes 因为过大的 `max_tokens` 卡住或失败

## 症状

Server 可以访问，但 Hermes 在生成时：

- 长时间卡住；
- timeout；
- 最终出现连接类错误。

## 原因

客户端请求的最大输出预算可能已经超过 server 的总 context budget。

例如：

```text
server context = 65536
Hermes max_tokens = 65536
```

这已经完全没有空间留给：

```text
system prompt
conversation history
tool schemas
user input
```

实际约束应理解成：

```text
prompt_tokens + max_tokens <= context_window
```

## 本仓库配置

```text
context_length = 81920
max_tokens     = 16384
```

于是大约留下：

```text
65536 tokens
```

给：

```text
system prompt
history
tool definitions
tool results
user content
```

同时最大输出为：

```text
16384 tokens
```

## Hermes 命令

```powershell
hermes config set model.context_length 81920
hermes config set model.max_tokens 16384
```

验证：

```powershell
hermes config get model.context_length
hermes config get model.max_tokens
```

---

# 6. `uv` 把包安装到了错误的 Python 环境

## 症状

你以为自己正在安装 TabbyAPI 的依赖，但输出却是：

```text
Using Python 3.13.x environment at:
E:\flash-next\.venv
```

而不是：

```text
E:\tabbyAPI\venv
```

## 为什么重要

PowerShell prompt 显示：

```text
(.venv)
```

并不能百分之百证明每一条 package-manager 命令实际使用的就是你想的那个 Python。

多项目、多 venv 并存时尤其容易踩坑。

## 更安全的写法

显式指定 Python：

```powershell
uv pip install `
  --python "E:\tabbyAPI\venv\Scripts\python.exe" `
  <package>
```

## 验证

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" --version
```

以及：

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" -c `
"import sys; print(sys.executable)"
```

预期：

```text
E:\tabbyAPI\venv\Scripts\python.exe
```

一个非常值得养成的习惯是：

> 不要只问“我激活了哪个 venv”，还要问“这条命令到底调用了哪个 python.exe”。

---

# 7. 大型 Torch wheel 因 TLS 失败

## 症状

安装 CUDA Torch 时反复出现：

```text
peer closed connection
```

或者：

```text
TLS close_notify
```

或者 Windows Schannel 错误。

数 GB 的 wheel 对不稳定网络非常敏感。

## 推荐策略

把：

```text
下载
```

和：

```text
安装
```

拆开。

先创建目录：

```powershell
New-Item -ItemType Directory -Force E:\tabbyAPI\wheels
```

然后使用支持断点续传的 curl：

```powershell
curl.exe -L -C - `
  --retry 50 `
  --retry-all-errors `
  --retry-delay 5 `
  --connect-timeout 20 `
  --ssl-no-revoke `
  -o "E:\tabbyAPI\wheels\torch.whl" `
  "<TORCH_WHEEL_URL>"
```

如果需要明确走本地代理，可加入：

```powershell
-x http://127.0.0.1:7897
```

最关键的参数：

```text
-C -
```

表示断点续传。

## 检查文件大小

```powershell
Get-Item "E:\tabbyAPI\wheels\torch.whl" |
  Select-Object Name, Length, @{
      Name="GiB"
      Expression={[math]::Round($_.Length / 1GB, 3)}
  }
```

然后从本地安装：

```powershell
uv pip install `
  --python "E:\tabbyAPI\venv\Scripts\python.exe" `
  "E:\tabbyAPI\wheels\torch.whl"
```

这样通常比 package manager 每次从头下载大型 wheel 更稳。

> 本仓库测试时使用的精确 Torch 版本为 `2.9.0+cu128`。具体 wheel URL 可能随上游版本变化，因此文档没有永久写死一个下载链接。

---

# 8. TabbyAPI `/v1/models` 出现奇怪目录名

## 症状

运行：

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

可能看到：

```text
.venv
flash-next-8gb
Qwen3.8-Flash-Next-exl3-3.05bpw
```

## 原因

TabbyAPI 会扫描：

```yaml
model_dir:
```

下面的目录。

例如：

```yaml
model_dir: E:\flash-next
```

而 `E:\flash-next` 下可能还有其他工程目录，并不全是模型。

## 处理

配置 Hermes 或测试 API 时，使用真正加载的模型 ID：

```text
Qwen3.8-Flash-Next-exl3-3.05bpw
```

不要假设 `/v1/models` 返回的每个目录都是真模型。

---

# 9. TabbyAPI 启动后占用大量 RAM

## 这是预期行为

本配置有意使用异构内存：

```yaml
cpu_moe_offload_layers: 999
```

MoE expert 会被移到 CPU / system RAM。

启动日志可能出现大量：

```text
CPU-offloaded experts (worker):
model.language_model.layers.X.mlp
```

这是正常的。

测试机器为：

```text
96 GB RAM
12 GB VRAM
```

也就是说，这套方案本来就是主动用富余 RAM 换取较低 VRAM 要求。

---

# 10. 如何理解 `sysmem_kv_cache`

例如：

```yaml
memory:
  sysmem_kv_cache: 2048
```

表示大约：

```text
2 GB
```

system-memory second-tier KV cache。

不要简单理解为：

```text
把 2 GB 正在使用的 GPU KV cache 永久搬到 RAM
```

更准确地说，它提供了额外的系统内存容量，用于 KV cache 的管理与复用。

本次测试：

```text
cache_size: 81920
cache_mode: FP16
sysmem_kv_cache: 2048
```

模型加载后 dedicated VRAM 静态占用约：

```text
10.5 GB
```

测试 GPU 总显存为 12 GB。

实际数字会受到：

```text
GPU model
driver
CUDA runtime
ExLlamaV3 version
quantization
other GPU applications
```

影响。

---

# 11. 增大 `sysmem_kv_cache` 不一定更快

更大的 system-RAM KV cache 可以在旧 KV 状态能够复用时，减少重复 prefill。

但是：

```text
RAM < VRAM
```

在延迟和靠近 GPU 的程度上存在明显差异，而且数据仍需要经过 CPU/GPU interconnect。

本质上是在比较：

```text
重新计算旧 KV
```

和：

```text
从 system RAM 恢复 / 复用 KV
```

对于很长、重复的 prefix，复用可能很划算。

对于短 prompt 或很少复用 cache 的工作流，更大二级 cache 可能收益不明显。

另外，本系统已经同时使用 CPU MoE offloading，因此 CPU / RAM 带宽以及 PCIe 数据通路本来就在参与推理。

因此：

> `sysmem_kv_cache` 应该通过实际 benchmark 调优，而不是默认“越大越快”。

---

# 12. 模型刚加载完就占用很高的 VRAM

## 现象

TabbyAPI 状态显示：

```text
cache 0/81,920 tokens in use
```

但 Windows 任务管理器里 dedicated GPU memory 已经很高。

这并不矛盾。

`0/81,920` 表示逻辑上当前没有活跃 token 使用该 cache。

但 GPU 显存可以已经被提前分配 / reserve 给：

```text
GPU-resident model components
KV cache capacity
runtime buffers
CUDA allocations
attention workspace
```

本次配置加载完成后约：

```text
10.5 / 12 GB
```

dedicated VRAM。

这已经非常接近消费级 12 GB GPU 的实际可用上限，因此运行模型时不建议同时启动其他大量占用 VRAM 的程序。

---

# 13. `python.exe` 打开 `>>>` 而不是运行 Server

## 症状

运行：

```powershell
.\venv\Scripts\python.exe
```

出现：

```text
Python 3.x.x ...
>>>
```

## 原因

你只启动了 Python 解释器，没有告诉它要执行什么脚本。

这条：

```powershell
python.exe
```

表示：

```text
打开 Python 交互式 REPL
```

而：

```powershell
python.exe main.py
```

才表示：

```text
用该 Python 运行 main.py
```

## 正确启动 TabbyAPI

```powershell
cd E:\tabbyAPI

& ".\venv\Scripts\python.exe" .\main.py
```

通用形式：

```text
<解释器> <脚本>
```

例如：

```text
python analysis.py
Rscript analysis.R
node server.js
```

---

# 14. `ModuleNotFoundError: No module named 'openai'`

## 症状

使用 TabbyAPI 自己的 Python 运行 tool-call 测试时：

```text
ModuleNotFoundError: No module named 'openai'
```

## 原因

TabbyAPI 作为 server 本身不一定需要 OpenAI Python SDK。

`openai` 包是测试客户端需要的。

## 方案一：安装到测试环境

```powershell
uv pip install `
  --python "E:\tabbyAPI\venv\Scripts\python.exe" `
  openai
```

## 方案二：使用 Hermes 自带 Python

Hermes 环境已经包含 OpenAI SDK：

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

---

# 15. Hermes 模型配置

本部署中建议：

```text
Provider:
Custom endpoint

API compatibility:
Chat Completions

Base URL:
http://127.0.0.1:8088/v1

Model:
Qwen3.8-Flash-Next-exl3-3.05bpw

Context length:
81920

Maximum output tokens:
16384
```

如果 TabbyAPI：

```yaml
disable_auth: true
```

API key 实际不会校验。

可以填：

```text
local
```

作为占位。

---

# 16. Chat Completions 与 Tool Calling 的关系

Tool calling 并不要求使用 OpenAI Responses API。

本配置已经实际验证：

```text
/v1/chat/completions
```

配合：

```text
tools=[...]
```

能够得到：

```text
finish_reason='tool_calls'
```

以及：

```text
tool_calls=[...]
```

因此 Hermes 这里正确的 compatibility mode 是：

```text
Chat Completions
```

关键不是使用 `/responses` 还是 `/chat/completions`，而是 backend 是否真正支持：

```text
tools
→ 模型工具格式
→ parser
→ structured tool_calls
```

---

# 17. 推荐排障顺序

当系统出问题时，按下面顺序。

## Step 1 — TabbyAPI 是否真的在运行？

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

如果失败，先处理 TabbyAPI / networking。

---

## Step 2 — 普通聊天是否工作？

发送一个基础 `/v1/chat/completions` 请求。

如果普通 generation 都失败，不要开始调 Hermes tools。

---

## Step 3 — Structured tool calling 是否工作？

运行：

```powershell
python scripts/test_tool_call.py
```

预期：

```text
PASS: Structured tool calling works.
```

---

## Step 4 — Hermes 是否真的执行工具？

使用不可预测测试值。

例如生成随机 UUID：

```powershell
$token = [guid]::NewGuid().ToString()
Set-Content "$env:TEMP\hermes_tool_test.txt" $token
$token
```

再让 Hermes 读取：

```powershell
hermes chat --oneshot --toolsets file `
  -q "You must use the file tool to read C:\Users\Administrator\AppData\Local\Temp\hermes_tool_test.txt and return its contents exactly. Do not guess."
```

成功时应该返回完全一致的 UUID，并报告至少一次真实 tool call。

这比测试文件里写：

```text
hello
```

可靠得多，因为随机 UUID 无法被模型猜中。

---

# 18. 快速诊断表

| 症状 | 最可能的问题层 |
|---|---|
| `/v1/models` 失败 | TabbyAPI / network |
| `curl` 正常，Python 失败 | proxy / Python HTTP client |
| 普通 chat 失败 | TabbyAPI / ExLlamaV3 / model |
| Chat 正常，`tool_calls=None` | tool parser / serving layer |
| `test_tool_call.py` PASS，Hermes 失败 | Hermes configuration |
| Hermes 说应该调用工具，但显示 `0 tool calls` | structured tool calling 没有到达 Hermes |
| 长请求卡住 | context / `max_tokens` budget |
| `uv` 装到错误目录 | wrong Python environment |
| Torch 安装不断重新下载 | large-wheel TLS / download |
| 模型加载后 RAM 很高 | CPU MoE offloading 的预期行为 |
| 空闲时 VRAM 仍很高 | 模型/cache/runtime 的预分配与 reserve |

---

# 19. 已验证的配置

测试使用：

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
  sysmem_kv_cache: 2048
```

这是一套经过实测的配置，并不是所有硬件上的全局最优。

不同：

```text
GPU
driver
model quantization
available RAM
available VRAM
```

都可能需要不同参数。

---

# 最终原则

调试本地 Agent 时，务必把下面三个问题拆开：

```text
模型能不能生成 tool call？
```

```text
Serving backend 能不能把它暴露成 structured tool_calls？
```

```text
Agent 能不能真正执行工具并把结果返回给模型？
```

这是三层不同的问题。

模型输出：

```text
I should call read_file
```

不能证明 structured tool calling 已经成功。

可靠的最终成功链路是：

```text
model
→ structured tool_calls
→ tool execution
→ tool result
→ final model response
```
