# Troubleshooting

This document collects the main issues encountered while running **Qwen3.8-Flash-Next EXL3 + ExLlamaV3 + TabbyAPI + Hermes Agent** on Windows.

The most important troubleshooting principle is:

> Do not debug the entire agent stack at once.

Test each layer independently:

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

# 1. Hermes reports `APIConnectionError`

## Symptom

Hermes fails with something similar to:

```text
APIConnectionError
```

while TabbyAPI or another local server appears to be running normally.

You may even find that:

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

works correctly.

## Possible cause: localhost traffic is being sent through a system proxy

This can happen on Windows when a VPN or proxy application configures environment/system proxies such as:

```text
127.0.0.1:7897
```

Python HTTP clients such as `httpx` may inherit these proxy settings.

As a result:

```text
Hermes
    ↓
httpx
    ↓
system proxy
    ↓
127.0.0.1:8088
```

instead of connecting directly to localhost.

## Check

Run:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  -c "import urllib.request; print(urllib.request.getproxies())"
```

If localhost requests are being affected by your proxy environment, test with:

```powershell
$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"
```

Then try Hermes again.

## Persistent fix

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

Open a new terminal afterward.

---

# 2. `curl` works, but Python/OpenAI SDK does not

## Symptom

This works:

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

but Python or Hermes fails.

## Why

Different HTTP clients may handle system proxy settings differently.

A successful `curl` request proves that:

```text
TabbyAPI is reachable
```

but does not necessarily prove that:

```text
Python httpx/OpenAI SDK is using the same route
```

## Test the exact Python environment

For Hermes:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  -c "import httpx; r=httpx.get('http://127.0.0.1:8088/v1/models'); print(r.status_code); print(r.text)"
```

If needed, compare with:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  -c "import httpx; c=httpx.Client(trust_env=False); r=c.get('http://127.0.0.1:8088/v1/models'); print(r.status_code); print(r.text)"
```

If `trust_env=False` works while the default fails, proxy inheritance is the likely cause.

---

# 3. Chat works, but tool calling does not

## Symptom

Normal chat requests work.

The model may even reason:

```text
I should call read_file...
```

but Hermes reports:

```text
0 tool calls
```

or the API response contains:

```text
tool_calls=None
```

## Important distinction

These are not equivalent:

```text
OpenAI-compatible chat server
```

and:

```text
OpenAI-compatible tool-calling server
```

A minimal `/v1/chat/completions` implementation may only support:

```text
messages
→ model
→ content
```

while ignoring:

```text
tools
tool_choice
tool_calls
```

## What happened in the original setup

The lightweight `serve.py` could serve normal chat completions, but it did not provide the full structured tool-calling pipeline required by Hermes.

The result was:

```text
Hermes sends messages + tools
        ↓
server handles messages
        ↓
tool definitions are not correctly passed/parsed
        ↓
model may verbally mention the tool
        ↓
server returns ordinary text
        ↓
Hermes receives no structured tool_calls
```

## Fix

Use TabbyAPI with:

```yaml
model:
  tool_format: qwen3_coder
```

and:

```yaml
model:
  tool_calls_in_reasoning: true
```

For Qwen3.8-Flash-Next, `qwen3_coder` is the critical parser used to convert model tool-call output into OpenAI-compatible structured `tool_calls`.

---

# 4. How to verify tool calling independently of Hermes

Do not test the complete Hermes stack first.

Run:

```powershell
python scripts/test_tool_call.py
```

or explicitly use a Python environment containing the OpenAI SDK:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

Expected result:

```text
Finish reason: tool_calls

PASS: Structured tool calling works.
Tool name: get_time
Arguments: {}
```

The important fields are:

```text
finish_reason='tool_calls'
```

and:

```text
tool_calls=[...]
```

A response such as:

```text
I should call get_time...
```

is **not** sufficient.

That is ordinary text, not a structured tool call.

## Interpretation

```text
test_tool_call.py PASS
+ Hermes tools PASS
→ full stack works
```

```text
test_tool_call.py PASS
+ Hermes tools FAIL
→ investigate Hermes configuration
```

```text
test_tool_call.py FAIL
→ investigate TabbyAPI / model / tool parser first
```

---

# 5. Hermes hangs or fails with a large `max_tokens`

## Symptom

The server appears reachable, but Hermes hangs, times out, or eventually reports a connection-related failure during generation.

## Cause

The client-side output budget may exceed the model server's total context budget.

For example:

```text
server context = 65536
Hermes max_tokens = 65536
```

already leaves no room for:

```text
system prompt
conversation history
tool schemas
user input
```

The actual constraint is approximately:

```text
prompt_tokens + max_tokens <= context_window
```

## Tested configuration

This repository uses:

```text
context_length = 81920
max_tokens     = 16384
```

This leaves approximately:

```text
65536 tokens
```

for:

```text
system prompt
history
tool definitions
tool results
user content
```

with up to:

```text
16384 tokens
```

for generation.

## Hermes commands

```powershell
hermes config set model.context_length 81920
hermes config set model.max_tokens 16384
```

Verify with:

```powershell
hermes config get model.context_length
hermes config get model.max_tokens
```

---

# 6. `uv` installs packages into the wrong Python environment

## Symptom

You believe you are installing into TabbyAPI, but output shows something like:

```text
Using Python 3.13.x environment at:
E:\flash-next\.venv
```

instead of:

```text
E:\tabbyAPI\venv
```

## Why this matters

A shell prompt such as:

```text
(.venv)
```

does not guarantee that every package manager command is targeting the Python environment you think it is.

## Safer pattern

Explicitly provide the Python executable:

```powershell
uv pip install `
  --python "E:\tabbyAPI\venv\Scripts\python.exe" `
  <package>
```

This is strongly recommended when multiple local model projects and virtual environments coexist.

## Verify

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" --version
```

and:

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" -c `
"import sys; print(sys.executable)"
```

Expected:

```text
E:\tabbyAPI\venv\Scripts\python.exe
```

---

# 7. Large Torch wheel download fails with TLS errors

## Symptom

Installing the CUDA build of Torch repeatedly fails with errors such as:

```text
peer closed connection
```

or:

```text
TLS close_notify
```

or Windows Schannel-related errors.

Large multi-gigabyte wheels are particularly vulnerable to unstable connections.

## Recommended approach

Separate:

```text
download
```

from:

```text
installation
```

instead of asking the package manager to repeatedly do both.

Example:

```powershell
New-Item -ItemType Directory -Force E:\tabbyAPI\wheels
```

Then use resumable download:

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

If using a local proxy:

```powershell
-x http://127.0.0.1:7897
```

can be added.

The important option is:

```text
-C -
```

which enables resume support.

## Verify downloaded size

```powershell
Get-Item "E:\tabbyAPI\wheels\torch.whl" |
  Select-Object Name, Length, @{
      Name="GiB"
      Expression={[math]::Round($_.Length / 1GB, 3)}
  }
```

Then install locally:

```powershell
uv pip install `
  --python "E:\tabbyAPI\venv\Scripts\python.exe" `
  "E:\tabbyAPI\wheels\torch.whl"
```

This is generally more robust than restarting a multi-gigabyte package download from scratch.

---

# 8. TabbyAPI's `/v1/models` shows unexpected directory names

## Symptom

The endpoint:

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

may return entries such as:

```text
.venv
flash-next-8gb
Qwen3.8-Flash-Next-exl3-3.05bpw
```

## Cause

TabbyAPI scans the configured:

```yaml
model_dir:
```

for model-like directories.

For example:

```yaml
model_dir: E:\flash-next
```

may contain multiple subdirectories unrelated to the actual model.

## Important

Use the actual loaded model ID:

```text
Qwen3.8-Flash-Next-exl3-3.05bpw
```

when configuring Hermes or running API tests.

Do not assume every entry returned by `/v1/models` is a valid model.

---

# 9. TabbyAPI starts, but model loading uses a large amount of RAM

## Expected behavior

This configuration intentionally uses heterogeneous memory:

```yaml
cpu_moe_offload_layers: 999
```

which moves MoE expert computation into CPU/system memory.

The startup log may contain many lines such as:

```text
CPU-offloaded experts (worker):
model.language_model.layers.X.mlp
```

This is expected.

The tested system has:

```text
96 GB RAM
12 GB VRAM
```

and uses RAM deliberately to make the model practical on a consumer GPU.

---

# 10. Understanding `sysmem_kv_cache`

Example:

```yaml
memory:
  sysmem_kv_cache: 2048
```

This configures approximately:

```text
2 GB
```

of system-memory second-tier KV cache.

It should not be interpreted as simply:

```text
2 GB of active GPU KV cache moved permanently into RAM
```

Instead, it provides additional system-memory capacity for KV cache reuse/management.

In the tested configuration:

```text
cache_size: 81920
cache_mode: FP16
sysmem_kv_cache: 2048
```

static dedicated VRAM usage after loading was approximately:

```text
10.5 GB
```

on a 12 GB NVIDIA GPU.

Actual usage varies by:

```text
GPU model
driver
CUDA runtime
ExLlamaV3 version
quantization
other GPU applications
```

---

# 11. Increasing `sysmem_kv_cache` may not always improve speed

A larger system-memory KV cache can reduce repeated prefill computation when previously computed KV states can be reused.

However, system RAM is slower than VRAM and data must travel across the CPU/GPU interconnect.

The tradeoff is approximately:

```text
recompute old KV
```

versus:

```text
restore/reuse KV from system RAM
```

For long repeated prefixes, reuse may be beneficial.

For short prompts or workloads with little cache reuse, a larger secondary cache may provide little benefit.

This system also uses CPU MoE offloading, so CPU/RAM bandwidth and PCIe traffic are already part of the inference path.

Therefore:

> Larger `sysmem_kv_cache` values should be benchmarked rather than assumed to be faster.

---

# 12. High static VRAM usage after model loading

## Example

The model may show high dedicated GPU memory immediately after startup even when:

```text
cache 0/81,920 tokens in use
```

This is not contradictory.

The first number refers to logical cache usage.

GPU memory can already be allocated or reserved for:

```text
GPU-resident model components
KV cache capacity
runtime buffers
CUDA allocations
attention workspace
```

In this setup, approximately:

```text
10.5 / 12 GB
```

of dedicated VRAM is used after loading.

This is close to the practical limit of the GPU, so avoid running other GPU-heavy applications at the same time.

---

# 13. `python.exe` opens `>>>` instead of running the server

## Symptom

Running:

```powershell
.\venv\Scripts\python.exe
```

produces:

```text
Python 3.x.x ...
>>>
```

## Explanation

You launched the Python interpreter without specifying a script.

This:

```powershell
python.exe
```

means:

```text
open the Python interactive REPL
```

while this:

```powershell
python.exe main.py
```

means:

```text
run main.py using this Python interpreter
```

## Correct TabbyAPI startup

```powershell
cd E:\tabbyAPI

& ".\venv\Scripts\python.exe" .\main.py
```

The general command pattern is:

```text
<interpreter> <script>
```

Examples:

```text
python analysis.py
Rscript analysis.R
node server.js
```

---

# 14. `ModuleNotFoundError: No module named 'openai'`

## Symptom

Running the tool-call test with the TabbyAPI Python environment returns:

```text
ModuleNotFoundError: No module named 'openai'
```

## Explanation

TabbyAPI does not necessarily need the OpenAI Python SDK to serve the API.

The SDK is only required by the test client.

## Options

Install it into a test environment:

```powershell
uv pip install `
  --python "E:\tabbyAPI\venv\Scripts\python.exe" `
  openai
```

or use Hermes' Python environment, where the OpenAI SDK is already installed:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

---

# 15. Hermes model configuration

For this deployment, Hermes should use:

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

If TabbyAPI is configured with:

```yaml
disable_auth: true
```

the API key is not actually validated.

A placeholder such as:

```text
local
```

is sufficient.

---

# 16. Chat Completions vs Tool Calling

Tool calling does not require the OpenAI Responses API.

This setup successfully uses:

```text
/v1/chat/completions
```

with:

```text
tools=[...]
```

and receives:

```text
finish_reason='tool_calls'
```

plus:

```text
tool_calls=[...]
```

Therefore the correct Hermes compatibility mode for this setup is:

```text
Chat Completions
```

The important issue is whether the backend correctly supports and parses structured tool calls, not whether it uses `/responses`.

---

# 17. Recommended debugging order

When something breaks, use this sequence.

## Step 1 — Is TabbyAPI running?

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

If this fails, debug TabbyAPI/networking first.

---

## Step 2 — Does plain chat work?

Send a basic `/v1/chat/completions` request.

If plain generation fails, do not debug Hermes tools yet.

---

## Step 3 — Does structured tool calling work?

Run:

```powershell
python scripts/test_tool_call.py
```

Expected:

```text
PASS: Structured tool calling works.
```

---

## Step 4 — Does Hermes execute the tool?

Use an unpredictable test value.

For example, create a random UUID:

```powershell
$token = [guid]::NewGuid().ToString()
Set-Content "$env:TEMP\hermes_tool_test.txt" $token
$token
```

Then ask Hermes:

```powershell
hermes chat --oneshot --toolsets file `
  -q "You must use the file tool to read C:\Users\Administrator\AppData\Local\Temp\hermes_tool_test.txt and return its contents exactly. Do not guess."
```

A successful result should contain the exact random UUID and report at least one tool call.

This is much stronger evidence than asking the model to read a file containing a predictable value such as:

```text
hello
```

because the model cannot guess a random UUID.

---

# 18. Quick diagnosis table

| Symptom | Most likely layer |
|---|---|
| `/v1/models` fails | TabbyAPI / network |
| `curl` works, Python fails | proxy / Python HTTP client |
| Plain chat fails | TabbyAPI / ExLlamaV3 / model |
| Chat works, `tool_calls=None` | tool parser / serving layer |
| `test_tool_call.py` passes, Hermes fails | Hermes configuration |
| Hermes says it should use a tool but reports `0 tool calls` | structured tool calling not reaching Hermes |
| Long requests hang | context / `max_tokens` budget |
| `uv` installs into wrong directory | wrong Python environment |
| Torch install repeatedly restarts | large-wheel TLS/download issue |
| Model loads but RAM usage is high | expected CPU MoE offloading |
| High static VRAM at idle | preallocated/reserved model/cache/runtime memory |

---

# 19. Known-good configuration

The configuration used during testing:

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

This is a tested configuration, not a universal optimum.

Hardware, driver versions, model quantization and available RAM/VRAM may require different values.

---

# Final principle

When debugging local agents, separate these three questions:

```text
Can the model generate a tool call?
```

```text
Can the serving backend expose it as structured tool_calls?
```

```text
Can the agent execute the tool and return the result?
```

These are three different layers.

A model saying:

```text
I should call read_file
```

does not prove that structured tool calling works.

The reliable success condition is:

```text
model
→ structured tool_calls
→ tool execution
→ tool result
→ final model response
```