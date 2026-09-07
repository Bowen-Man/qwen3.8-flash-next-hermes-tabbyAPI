# 性能调优指南

[English](tuning.md) | **简体中文**

本文介绍在消费级 NVIDIA GPU 上运行 **Qwen3.8-Flash-Next EXL3 + ExLlamaV3 + TabbyAPI** 时，最重要的性能与内存取舍。

本文实际测试机器：

```text
GPU: 12 GB VRAM
RAM: 96 GB
CPU: AMD Ryzen 9 9950X3D
Model: Qwen3.8-Flash-Next EXL3 3.05 bpw
Context: 81,920
Primary KV cache: FP16
System-memory KV cache: 2048 MB
CPU MoE offload: 所有可 offload layers
```

> 这是一套实用调优参考，不是所有机器的通用最优解。

---

# 1. 先用“异构内存”理解这套方案

这套配置并不是试图把整个模型都塞进 VRAM, 而是：
```text
GPU VRAM
├── GPU 常驻模型组件
├── attention compute
├── active / primary KV cache
└── runtime buffers

System RAM
├── CPU-offloaded MoE experts
└── second-tier KV cache

NVMe SSD
└── n-gram embedding table
```

核心目标是：
> **把对延迟敏感的工作尽量留在 GPU，把主要占容量的部分交给 RAM 或 SSD。**

---

# 2. `cpu_moe_offload_layers`

本文测试：

```yaml
cpu_moe_offload_layers: 999
```

取 `999` 等足够大的数值，令所有符合条件的 MoE layers 进入 CPU inference。

对于小显存机器，这可能是**最关键的配置**之一。

## 优点

- 大幅降低 VRAM 压力；
- 让大型 MoE 模型可以在消费级 GPU 上运行；
- 能充分利用大容量 RAM 和高性能 CPU。

## 代价

- CPU compute 会参与几乎每一个 token 的生成；
- RAM bandwidth 会变得重要；
- CPU↔GPU 同步/传输可能成为瓶颈；
- decode speed 可能低于更多层留在 GPU 的配置。

## 建议

对于 12 GB VRAM，可以先从：

```yaml
cpu_moe_offload_layers: 999
```

开始。

只有在确认 VRAM 明显有富余后，才考虑减少 CPU offload。

---

# 3. `cache_mode`

本文测试：

```yaml
cache_mode: FP16
```

FP16 KV cache 精度高，但显存占用比量化 cache 更高。

如果模型能稳定装入显存，并且实际运行不 OOM，FP16 是一个合理的默认选择。

如果显存不足，可以考虑：

```yaml
cache_mode: Q8
```

或 TabbyAPI 支持的其他低 bit cache。

大致取舍：

```text
FP16
→ 更高显存占用
→ 不量化 KV

Q8 / 更低 bit
→ 更低显存占用
→ KV cache 被量化
```

不要仅仅为了把已经安全的显存数字进一步压低，就主动牺牲 FP16。

---

# 4. `cache_size` 和 `max_seq_len`

本文测试：

```yaml
max_seq_len: 81920
cache_size: 81920
```

它们决定了 server 实际提供的 context capacity。

上下文越长，cache 所需内存越多。

如果出现 OOM，减少 context 往往是最干净的回退方式之一。

可以尝试：

```text
81920
↓
76800
↓
65536
```

对于 Agent 工作负载，65K+ context 仍然很有价值，因为：

```text
system prompt
tool schemas
conversation history
tool results
```

本身就会占掉大量 token。

---

# 5. Hermes 输出预算

本文 Hermes 配置：

```text
context_length = 81920
max_tokens     = 16384
```

输出预算必须给输入 prompt 留出空间。

可以理解成：

```text
81,920 total
├── ~65,536 prompt / history / tools
└── ≤16,384 generation
```

不要设置：

```text
max_tokens == context_length
```

否则从预算上看几乎没有空间留给真正的 prompt。

---

# 6. `sysmem_kv_cache`

本文测试：

```yaml
memory:sysmem_kv_cache: 2048
```

也就是约 2 GB 的 system-memory second-tier KV cache。

在本文机器上，模型加载后的 dedicated GPU memory 静态占用约：

```text
10.5 GB / 12 GB
```

## 重要：不用简单减法理解sysmem_kv_cache

它不是：

```text
VRAM KV - 2 GB = RAM KV
```

这种关系。

它是一个二级 cache 机制，主要影响 cache management 和 reuse。

## 为什么不是越大越好？

当 KV 状态需要复用时，RAM 里的内容仍然可能需要重新进入 GPU 侧的数据路径。

本质上的竞争是：

```text
重新计算 KV vs 从 RAM 恢复 / 复用 KV
```

如果 prefix 很长且重复度高，reuse 可能很划算。

如果 prompt 很短或者几乎没有 reuse，把 secondary cache 调得很大可能几乎没有收益。

---

# 7. `ngram_ram`

本文测试：

```yaml
ngram_ram: false
```

Qwen3.8-Flash-Next 使用 n-gram embedding table。

当设为 `false` 时，它不会把整张表完全加载进 RAM，而是从存储设备读取。

这可以减少 RAM 压力。

## 建议

使用速度较快的 NVMe SSD。

如果 RAM 极其充裕，可以单独 benchmark：

```yaml
ngram_ram: true
```

但不默认它一定更快。

---

# 8. `chunk_size`

本文测试：

```yaml
chunk_size: 2048
```

这个参数主要影响 prompt ingestion / prefill。

大致趋势：

```text
更大的 chunk
→ 某些情况下 prefill 更快
→ 可能增加显存压力

更小的 chunk
→ 降低峰值内存
→ ingestion 可能更慢
```

比较实际的测试范围：

```text
1024
2048
4096
```

对于本文 12 GB 系统，`2048` 是一个合理基线。

---

# 9. `max_batch_size`

本文测试：

```yaml
max_batch_size: 1
```

对于单用户本地 Agent，一般不需要并发。

使用：

```yaml
max_batch_size: 1
```

可以尽量减少额外显存开销。只有明确需要并发请求时，再提高它。

---

# 10. `output_chunking`

本文测试：

```yaml
output_chunking: true
```

它让 output/cache allocation 可以按 chunk 增长，而不是一开始就为整个 completion budget 分配全部空间。

对于显存紧张的本地部署，通常建议保持开启。

---

# 11. 如果模型装不下，先改什么？

推荐顺序：

```text
1. 保持较高 CPU MoE offloading
2. 降低 context
3. 考虑量化 KV cache
4. 降低 chunk_size
5. 不要开不必要的 batch concurrency
```

如果模型已经装得下，但速度不满意：

```text
1. 测 decode tok/s
2. 测 TTFT / prefill
3. 看 CPU utilization
4. 看 RAM bandwidth 压力
5. 看 SSD activity
6. 最后再考虑把更多工作搬回 GPU
```

不要只看任务管理器里的显存数字做优化。

---

# 12. 真正值得 benchmark 的指标

对于 Agent 工作负载，建议记录：

| 指标 | 为什么重要 |
|---|---|
| 模型加载后的静态 VRAM | 判断容量与安全余量 |
| 模型加载后的 RAM 使用 | 判断 CPU offload 成本 |
| TTFT | 用户实际感受到的首 token 延迟 |
| Prefill speed | 长上下文性能 |
| Decode tok/s | 实际生成速度 |
| 8K prompt TTFT | 短/中等上下文 |
| 32K prompt TTFT | 较长 Agent history |
| 64K prompt TTFT | 接近长上下文极限 |
| Tool-call success rate | Agent 可靠性 |
| Repeated-prefix TTFT | KV cache reuse 是否有效 |

---

# 13. Benchmark 模板

不同配置比较时，使用同一模型和同一 prompt。

| 配置 | Static VRAM | Free RAM | Context | KV mode | sysmem KV | TTFT | Decode tok/s | Tool call |
|---|---:|---:|---:|---|---:|---:|---:|---|
| Baseline | | | 81920 | FP16 | 2048 MB | | | ✅ |
| Variant A | | | | | | | | |
| Variant B | | | | | | | | |

每次只改变一个参数，其余参数保持完全一致。

否则你无法判断性能变化究竟来自哪里。

---

# 14. 一个很重要的调优思想

当模型还装不进去时：

```text
主要矛盾 = 容量
```

当模型已经能装进去以后：

```text
主要矛盾 = 数据移动 + 计算平衡
```

在异构推理中，总性能取决于：

```text
GPU compute
+
CPU compute
+
RAM bandwidth
+
CPU↔GPU transfer
+
SSD access
```

所以：

> **更多 offload、更大的 RAM cache、更低的 VRAM 使用量，都不等于更快。**

---

# 15. 当前已验证 baseline

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

本文机器观察到：

```text
Static dedicated VRAM after loading: ~10.5 GB / 12 GB
```
作为参考基线即可，并非所有机器都应得到的固定结果。

---

# 16. 最终建议

对于 12 GB GPU + 大容量系统 RAM：

```text
先保证稳定
→ 再确认 tool calling
→ 测真实 Agent workload
→ 每次只改一个参数
```

一个“更省显存”或者“更吃 RAM”的配置，不一定更好。

真正的 sweet spot 应同时满足：

```text
模型稳定加载
+
可接受 TTFT
+
可接受 decode speed
+
长上下文稳定
+
tool calling 稳定
```
