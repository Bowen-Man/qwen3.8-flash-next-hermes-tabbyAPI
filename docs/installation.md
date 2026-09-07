# Installation Guide

This guide walks through a complete Windows deployment of:

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

The goal is not only to make the model generate text.

The final success condition is:

```text
Hermes sends tool definitions
        ↓
Qwen chooses a tool
        ↓
TabbyAPI returns structured OpenAI tool_calls
        ↓
Hermes executes the tool
        ↓
The tool result is returned to Qwen
        ↓
Qwen produces the final answer
```

---

# 1. Tested environment

The following configuration has been tested successfully:

| Component | Tested configuration |
|---|---|
| OS | Windows 11 |
| CPU | AMD Ryzen 9 9950X3D |
| GPU | NVIDIA GPU, 12 GB VRAM |
| System RAM | 96 GB |
| TabbyAPI Python | Python 3.12.13 |
| Torch | 2.9.0+cu128 |
| ExLlamaV3 | 1.4.8 |
| Model | Qwen3.8-Flash-Next EXL3 3.05 bpw |
| Context | 81,920 tokens |
| KV cache | FP16 |
| System-memory KV cache | 2 GB |
| Agent | Hermes Agent |
| API mode | OpenAI Chat Completions |

This is a **tested configuration**, not a minimum hardware requirement.

Different GPUs, quantizations and memory configurations may require different cache or offload settings.

---

# 2. What you need before starting

You need:

- Windows 10/11
- an NVIDIA GPU
- a recent NVIDIA driver
- Git
- Python 3.12
- enough system RAM for CPU MoE offloading
- a Qwen3.8-Flash-Next EXL3 model
- Hermes Agent
- TabbyAPI

This guide assumes a CUDA 12.x setup.

For the exact tested configuration, Python 3.12 is recommended.

Check Python:

```powershell
py -3.12 --version
```

Expected:

```text
Python 3.12.x
```

Check the GPU:

```powershell
nvidia-smi
```

---

# 3. Prepare the EXL3 model

This guide uses:

```text
Qwen3.8-Flash-Next-exl3-3.05bpw
```

The model can be stored anywhere.

Example:

```text
E:\flash-next\
└── Qwen3.8-Flash-Next-exl3-3.05bpw\
```

The important distinction is:

```text
model_dir
    ↓
E:\flash-next

model_name
    ↓
Qwen3.8-Flash-Next-exl3-3.05bpw
```

Do not set both values to the complete model path.

---

# 4. Install TabbyAPI

Clone the official `theroyallab/tabbyAPI` repository from GitHub.

For example, choose:

```text
E:\tabbyAPI
```

as the installation directory.

The resulting structure should look approximately like:

```text
E:\tabbyAPI\
├── main.py
├── start.bat
├── config_sample.yml
├── pyproject.toml
└── ...
```

---

# 5. Install the inference environment

## Recommended Windows method

Open PowerShell:

```powershell
cd E:\tabbyAPI
.\start.bat
```

During first launch, TabbyAPI will create its own virtual environment and install the required inference dependencies.

Select the CUDA 12.x option when prompted.

The environment should end up under:

```text
E:\tabbyAPI\venv
```

Verify:

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" --version
```

The tested setup uses:

```text
Python 3.12.13
```

---

# 6. Verify Torch and CUDA

After installation:

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" -c `
"import torch; print('Torch:', torch.__version__); print('CUDA:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```

A tested setup reports approximately:

```text
Torch: 2.9.0+cu128
CUDA: 12.8
CUDA available: True
GPU: NVIDIA ...
```

Then verify ExLlamaV3:

```powershell
& "E:\tabbyAPI\venv\Scripts\python.exe" -c `
"import torch, exllamav3; print('Torch:', torch.__version__); print('ExLlamaV3: OK')"
```

Expected:

```text
ExLlamaV3: OK
```

---

# 7. If the large Torch download repeatedly fails

The CUDA Torch wheel is several gigabytes.

On unstable connections, VPNs or some Windows proxy configurations, installation may fail with TLS errors such as:

```text
peer closed connection
```

or:

```text
missing close_notify
```

Do not repeatedly reinstall the entire environment.

A more reliable strategy is:

```text
download the wheel once with resume support
        ↓
verify the file
        ↓
install the local wheel
```

See:

```text
docs/troubleshooting.md
```

for the resumable download procedure.

---

# 8. Create `config.yml`

TabbyAPI ships with:

```text
config_sample.yml
```

Create:

```text
E:\tabbyAPI\config.yml
```

You may copy this repository's:

```text
config/config.example.yml
```

and edit the model path.

A tested configuration is:

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

---

# 9. Understand the important settings

## Context

```yaml
max_seq_len: 81920
cache_size: 81920
```

The tested server exposes an 81,920-token context.

`cache_size` must be large enough for the configured sequence length.

---

## KV cache

```yaml
cache_mode: FP16
```

The tested setup keeps the primary KV cache in FP16.

On GPUs with less available VRAM, quantized KV cache modes may be required.

---

## CPU MoE offloading

```yaml
cpu_moe_offload_layers: 999
```

Qwen3.8-Flash-Next is a mixture-of-experts model.

A large value such as:

```text
999
```

causes all eligible MoE layers to be CPU-offloaded.

This is one of the key reasons the model can run on a relatively small consumer GPU.

During model loading, logs should contain many messages similar to:

```text
CPU-offloaded experts (worker):
model.language_model.layers.X.mlp
```

This is expected.

---

# 10. Qwen n-gram storage

```yaml
ngram_ram: false
```

Qwen3.8-Flash-Next uses an n-gram embedding table.

With:

```yaml
ngram_ram: false
```

the table is not fully loaded into system RAM.

This reduces RAM consumption at the cost of using storage during inference.

A fast SSD/NVMe drive is recommended.

---

# 11. System-memory KV cache

The tested setup uses:

```yaml
memory:
  sysmem_kv_cache: 2048
```

This provides approximately:

```text
2 GB
```

of second-tier KV cache in system RAM.

On the tested 12 GB GPU, this configuration results in approximately:

```text
10.5 GB
```

of static dedicated GPU memory after loading.

This number is hardware- and runtime-dependent and should not be treated as a universal result.

---

# 12. The most important Agent setting

This line is essential:

```yaml
tool_format: qwen3_coder
```

Without a compatible tool parser, normal chat may work while structured Agent tool calling fails.

The distinction is:

```text
Model output:
"I should call read_file"
```

versus:

```text
OpenAI response:
finish_reason = tool_calls
tool_calls = [...]
```

Hermes needs the second form.

The model merely mentioning a tool in ordinary text is not enough.

---

# 13. Start TabbyAPI

Once the environment is installed, direct startup is recommended for this tested setup:

```powershell
cd E:\tabbyAPI

& ".\venv\Scripts\python.exe" .\main.py
```

This explicitly means:

```text
E:\tabbyAPI\venv\Scripts\python.exe
                ↓
             runs
                ↓
E:\tabbyAPI\main.py
```

Unlike running the startup installer again, this starts the existing configured environment directly.

Keep this PowerShell window open while using the model.

---

# 14. Confirm successful model loading

Expected logs include:

```text
CPU-offloaded experts (worker): ...
```

followed by:

```text
Model loaded in ...
```

and:

```text
Serving OAI API on 127.0.0.1:8088
```

The status line should show:

```text
cache 0/81,920 tokens in use
```

At this point:

```text
TabbyAPI
    ↓
ExLlamaV3
    ↓
Qwen3.8-Flash-Next
```

is running.

Hermes is not involved yet.

---

# 15. Verify the API server

Open a second PowerShell window:

```powershell
curl.exe http://127.0.0.1:8088/v1/models
```

You should see the model:

```text
Qwen3.8-Flash-Next-exl3-3.05bpw
```

Use this exact model ID later when configuring Hermes.

If other directory names also appear, use the actual loaded model name rather than assuming every returned entry is valid.

---

# 16. Verify structured tool calling before configuring Hermes

This repository contains:

```text
scripts/test_tool_call.py
```

The script deliberately bypasses Hermes.

It tests only:

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

This makes debugging much easier.

---

# 17. Prepare a small test environment

From this repository:

```powershell
cd E:\GitHub\qwen3.8-flash-next-hermes-tabbyAPI

py -3.12 -m venv venv

& ".\venv\Scripts\python.exe" -m pip install openai
```

Then run:

```powershell
& ".\venv\Scripts\python.exe" `
  ".\scripts\test_tool_call.py"
```

---

# 18. Expected tool-call test result

Successful output should resemble:

```text
Model: Qwen3.8-Flash-Next-exl3-3.05bpw
Finish reason: tool_calls

Content: None

PASS: Structured tool calling works.
Tool name: get_time
Arguments: {}
```

The critical success conditions are:

```text
finish_reason = tool_calls
```

and:

```text
tool_calls != None
```

This is not sufficient:

```text
I should call get_time...
```

That is only ordinary generated text.

If the script reports:

```text
PASS: Structured tool calling works.
```

then the model-serving layer is ready for an Agent.

---

# 19. Install Hermes Agent

Install Hermes Agent using the current official Windows installer or Hermes Desktop installer.

After installation, open a new PowerShell window and verify:

```powershell
hermes --version
```

Then check the installation:

```powershell
hermes doctor
```

Resolve core installation failures before continuing.

Optional provider integrations are not required for the local TabbyAPI model itself.

---

# 20. Configure Hermes

Run:

```powershell
hermes model
```

Choose:

```text
Custom endpoint
```

For API compatibility choose:

```text
Chat Completions
```

Use:

```text
Base URL:
http://127.0.0.1:8088/v1

Model:
Qwen3.8-Flash-Next-exl3-3.05bpw

API key:
local
```

Because the example TabbyAPI configuration uses:

```yaml
disable_auth: true
```

the API key is not validated.

The placeholder:

```text
local
```

is sufficient.

Do not expose a server configured with `disable_auth: true` to untrusted networks.

---

# 21. Configure Hermes context

When Hermes asks for context length, use:

```text
81920
```

Then explicitly configure the maximum output budget:

```powershell
hermes config set model.context_length 81920
hermes config set model.max_tokens 16384
```

Verify:

```powershell
hermes config get model.context_length
hermes config get model.max_tokens
```

Expected:

```text
81920
16384
```

The approximate token budget is therefore:

```text
81,920 total context
│
├── ~65,536 available for:
│      system prompt
│      conversation history
│      tool schemas
│      tool results
│
└── up to 16,384 output tokens
```

This prevents the client from requesting an output budget that consumes the entire server context window.

---

# 22. Verify normal Hermes chat first

Before testing tools:

```powershell
hermes chat --oneshot --toolsets clarify `
  -q "What model are we using?"
```

A normal model response confirms:

```text
Hermes
    ↓
TabbyAPI
    ↓
Qwen
```

works.

Do not debug Agent tools until ordinary chat succeeds.

---

# 23. Perform a real Agent integration test

A tool-call parser test proves that structured tool calls exist.

It does **not** prove that Hermes actually executes them.

For the final integration test, create a file containing a random UUID:

```powershell
$token = [guid]::NewGuid().ToString()

Set-Content "$env:TEMP\hermes_tool_test.txt" $token

$token
```

The value is intentionally random so the model cannot guess it.

---

# 24. Ask Hermes to read the file

Run:

```powershell
hermes chat --oneshot --toolsets file `
  -q "You must use the file tool to read C:\Users\Administrator\AppData\Local\Temp\hermes_tool_test.txt and return its contents exactly. Do not guess."
```

A successful Agent loop should:

1. emit a structured `read_file` tool call;
2. let Hermes execute the tool;
3. return the random UUID;
4. report at least one actual tool call.

The complete successful path is:

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

At this point the deployment is functioning as a real local Agent backend.

---

# 25. Daily startup

Once everything is installed, the model server only needs:

```powershell
cd E:\tabbyAPI

& ".\venv\Scripts\python.exe" .\main.py
```

Wait until:

```text
Model loaded
```

and:

```text
Serving OAI API on 127.0.0.1:8088
```

appear.

Leave that terminal running.

Then open another terminal and use:

```powershell
hermes
```

When the TabbyAPI terminal closes:

```text
Python process stops
        ↓
model unloads
        ↓
port 8088 closes
        ↓
Hermes can no longer reach the model
```

---

# 26. Recommended validation order

Whenever reinstalling or changing the configuration, validate in this order:

```text
1. GPU visible
        ↓
2. Torch + CUDA work
        ↓
3. ExLlamaV3 imports
        ↓
4. TabbyAPI loads model
        ↓
5. /v1/models works
        ↓
6. test_tool_call.py passes
        ↓
7. Hermes normal chat works
        ↓
8. Hermes real file-tool test works
```

Do not test all layers simultaneously.

---

# 27. What each component actually does

Understanding the layers makes troubleshooting much easier.

```text
Hermes Agent
│
│  Agent orchestration
│  tool execution
│  conversation loop
│
▼
TabbyAPI
│
│  OpenAI-compatible API server
│  chat templates
│  tool schema handling
│  qwen3_coder parser
│
▼
ExLlamaV3
│
│  inference engine
│  GPU execution
│  CPU MoE offloading
│  cache management
│
▼
Qwen3.8-Flash-Next EXL3
│
│  model weights
│  reasoning
│  tool-selection capability
│
▼
GPU + CPU + RAM + SSD
```

A failure in one layer does not automatically mean the model itself is broken.

---

# 28. Tested memory architecture

The tested 12 GB deployment approximately uses:

```text
GPU VRAM
├── GPU-resident model components
├── attention
├── primary FP16 KV cache
└── runtime buffers

System RAM
├── CPU-offloaded MoE experts
└── 2 GB second-tier KV cache

NVMe SSD
└── n-gram embedding table
```

This is why the setup should be considered heterogeneous inference rather than simply "loading a huge model into a 12 GB GPU."

---

# 29. If something fails

See:

```text
docs/troubleshooting.md
```

for:

- localhost proxy issues;
- `APIConnectionError`;
- `curl` works but Python fails;
- tool calling returns ordinary text;
- `uv` installs into the wrong environment;
- large Torch wheel TLS failures;
- context / `max_tokens` conflicts;
- unexpected `/v1/models` entries;
- RAM / VRAM behavior;
- second-tier KV cache behavior.

---

# 30. Final success checklist

Your installation is complete when all of the following are true:

```text
[ ] TabbyAPI loads the EXL3 model

[ ] CUDA is available

[ ] /v1/models returns the model ID

[ ] scripts/test_tool_call.py reports PASS

[ ] finish_reason is tool_calls

[ ] Hermes normal chat works

[ ] Hermes can execute a real file tool

[ ] Hermes returns an unpredictable UUID read from disk
```

If all checks pass, the complete local Agent stack is operational:

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
