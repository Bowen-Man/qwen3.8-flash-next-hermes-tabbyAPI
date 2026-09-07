"""Benchmark a local OpenAI-compatible chat endpoint.

Examples
--------
Short baseline:
    python benchmark_chat.py

Long-context benchmark:
    python benchmark_chat.py --prompt-tokens 32000
    python benchmark_chat.py --prompt-tokens 64000 --cache-reuse

Repeat a configuration three times and report medians:
    python benchmark_chat.py --prompt-tokens 64000 --cache-reuse --runs 3

Another local backend/model:
    python benchmark_chat.py --base-url http://127.0.0.1:1234/v1 \
        --model your-model-id --prompt-tokens 32000 --cache-reuse

Notes
-----
- --prompt-tokens targets the server-reported chat prompt token count.
- The script performs small calibration requests before the benchmark.
- Each independent run uses a unique nonce to avoid accidental reuse across runs.
- With --cache-reuse, the second request in each run uses the exact same prompt.
- Cached prompt_tokens / TTFT is an effective reuse rate, not physical prefill speed.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
import uuid
from dataclasses import dataclass

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment]


DEFAULT_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8088/v1")
DEFAULT_MODEL = os.getenv("LOCAL_LLM_MODEL", "Qwen3.8-Flash-Next-exl3-3.05bpw")
DEFAULT_API_KEY = os.getenv("LOCAL_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "local"))

SHORT_PROMPT = (
    "Explain why structured tool calling requires cooperation between the model, "
    "the serving backend, and the agent runtime. Keep the answer concise."
)
QUESTION = (
    "\n\nUsing the context above only as benchmark filler, briefly explain why "
    "structured tool calling requires cooperation between the model, serving "
    "backend, and agent runtime."
)
FILLER_UNIT = "benchmark context data block. "


@dataclass
class Result:
    label: str
    ttft: float | None
    total_time: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    generated_chars: int
    content: str
    reasoning: str

    @property
    def decode_time(self) -> float | None:
        if self.ttft is None:
            return None
        value = self.total_time - self.ttft
        return value if value > 0 else None

    @property
    def decode_tps(self) -> float | None:
        if self.decode_time and self.completion_tokens:
            return self.completion_tokens / self.decode_time
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark a local OpenAI-compatible chat endpoint."
    )
    parser.add_argument(
        "--prompt-tokens",
        type=int,
        default=None,
        help="Target server-reported prompt tokens, e.g. 8000, 16000, 32000, 64000.",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=256,
        help="Maximum completion tokens (default: 256)."
    )
    parser.add_argument(
        "--cache-reuse", action="store_true",
        help="Send the exact same prompt twice in each run to test prefix reuse."
    )
    parser.add_argument(
        "--runs", type=int, default=1,
        help="Number of independent benchmark cycles (default: 1)."
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL,
        help=f"OpenAI-compatible base URL (default: {DEFAULT_BASE_URL})."
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Model ID (default: {DEFAULT_MODEL})."
    )
    parser.add_argument(
        "--api-key", default=DEFAULT_API_KEY,
        help="API key. Defaults to LOCAL_LLM_API_KEY / OPENAI_API_KEY / 'local'."
    )
    parser.add_argument(
        "--context-limit", type=int, default=81920,
        help="Context limit used only for a safety warning (default: 81920; use 0 to disable)."
    )
    return parser.parse_args()


def one_token_probe(client: OpenAI, model: str, prompt: str) -> int:
    usage = None
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1,
        temperature=0,
        stream=True,
        stream_options={"include_usage": True},
    )
    for chunk in stream:
        if chunk.usage is not None:
            usage = chunk.usage
    if usage is None:
        raise RuntimeError(
            "The server did not return token usage during streamed calibration. "
            "This benchmark needs server-reported prompt_tokens."
        )
    return usage.prompt_tokens


def calibration_prompt(repeats: int) -> str:
    return (
        f"Calibration nonce: {uuid.uuid4().hex}\n"
        "Ignore the following filler. This request only measures tokenization.\n"
        + (FILLER_UNIT * repeats)
        + QUESTION
    )


def estimate_repetitions(client: OpenAI, model: str, target_tokens: int) -> tuple[int, float, float]:
    small_repeats, large_repeats = 256, 1024
    small_tokens = one_token_probe(client, model, calibration_prompt(small_repeats))
    large_tokens = one_token_probe(client, model, calibration_prompt(large_repeats))
    tokens_per_repeat = (large_tokens - small_tokens) / (large_repeats - small_repeats)
    if tokens_per_repeat <= 0:
        raise RuntimeError("Calibration produced an invalid token/repetition estimate.")
    overhead = small_tokens - small_repeats * tokens_per_repeat
    repetitions = max(round((target_tokens - overhead) / tokens_per_repeat), 1)
    return repetitions, tokens_per_repeat, overhead


def build_long_prompt(repetitions: int, nonce: str) -> str:
    return (
        f"Benchmark nonce: {nonce}\n"
        "The following text is synthetic benchmark context. "
        "Do not summarize it; use it only to create a long context window.\n\n"
        + (FILLER_UNIT * repetitions)
        + QUESTION
    )


def run_stream(client: OpenAI, model: str, prompt: str, max_tokens: int, label: str) -> Result:
    start = time.perf_counter()
    first_token_time = None
    reasoning_parts: list[str] = []
    content_parts: list[str] = []
    usage = None

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0,
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        if chunk.usage is not None:
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)
        content = delta.content
        if reasoning:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            reasoning_parts.append(reasoning)
        if content:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            content_parts.append(content)

    end = time.perf_counter()
    return Result(
        label=label,
        ttft=(first_token_time - start) if first_token_time else None,
        total_time=end - start,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        generated_chars=len("".join(reasoning_parts) + "".join(content_parts)),
        content="".join(content_parts),
        reasoning="".join(reasoning_parts),
    )


def print_result(result: Result, requested_tokens: int | None, cached: bool = False) -> None:
    print(f"\n=== {result.label} ===")
    if requested_tokens is not None:
        print(f"Requested prompt target: {requested_tokens:,} tokens")
    if result.prompt_tokens is not None:
        print(f"Actual prompt tokens:     {result.prompt_tokens:,}")
        if requested_tokens:
            error = result.prompt_tokens - requested_tokens
            error_pct = 100 * error / requested_tokens
            print(f"Target error:             {error:+,} tokens ({error_pct:+.2f}%)")
    print(f"TTFT:                     {result.ttft:.3f} s" if result.ttft is not None else "TTFT:                     n/a")
    print(f"Total time:               {result.total_time:.3f} s")
    print(f"Generated characters:     {result.generated_chars:,}")
    if result.decode_time:
        print(f"Generated characters/sec: {result.generated_chars / result.decode_time:.1f}")
    if result.completion_tokens is not None:
        print(f"Completion tokens:        {result.completion_tokens:,}")
    if result.total_tokens is not None:
        print(f"Total tokens:             {result.total_tokens:,}")
    if result.decode_tps is not None:
        print(f"Approx. decode throughput: {result.decode_tps:.2f} tok/s")
    if result.ttft and result.prompt_tokens:
        rate = result.prompt_tokens / result.ttft
        if cached:
            print(f"Effective cached-prefix rate: {rate:.1f} tok/s")
        else:
            print(f"Approx. first-pass prompt rate: {rate:.1f} tok/s")


def median_or_none(values: list[float | None]) -> float | None:
    finite = [v for v in values if v is not None]
    return statistics.median(finite) if finite else None


def main() -> None:
    args = parse_args()
    if OpenAI is None:
        raise SystemExit("Missing dependency: openai. Install it with: pip install openai")
    if args.prompt_tokens is not None and args.prompt_tokens < 256:
        raise SystemExit("--prompt-tokens must be at least 256.")
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1.")
    if args.context_limit and args.prompt_tokens is not None:
        if args.prompt_tokens + args.max_tokens > args.context_limit:
            print(
                f"WARNING: prompt target + max output exceeds the configured "
                f"--context-limit ({args.context_limit:,})."
            )

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)
    print(f"Base URL: {args.base_url}")
    print(f"Model: {args.model}")
    print(f"Max output tokens: {args.max_tokens}")
    print(f"Independent runs: {args.runs}")

    repetitions = None
    requested_tokens = args.prompt_tokens
    if args.prompt_tokens is not None:
        print(f"Requested prompt target: {args.prompt_tokens:,} tokens")
        print("Calibrating against server-reported token usage...")
        repetitions, tokens_per_repeat, overhead = estimate_repetitions(client, args.model, args.prompt_tokens)
        print(f"Estimated tokens/filler unit: {tokens_per_repeat:.3f}")
        print(f"Estimated chat/template overhead: {overhead:.1f} tokens")
        print(f"Filler repetitions: {repetitions:,}")

    first_results: list[Result] = []
    cached_results: list[Result] = []

    for i in range(1, args.runs + 1):
        if repetitions is None:
            prompt = SHORT_PROMPT
        else:
            prompt = build_long_prompt(repetitions, uuid.uuid4().hex)

        first = run_stream(client, args.model, prompt, args.max_tokens, f"Cycle {i} — first pass")
        first_results.append(first)
        print_result(first, requested_tokens, cached=False)

        if args.cache_reuse:
            second = run_stream(client, args.model, prompt, args.max_tokens, f"Cycle {i} — exact-prefix reuse")
            cached_results.append(second)
            print_result(second, requested_tokens, cached=True)
            if first.ttft and second.ttft:
                print("\n--- Cache reuse comparison ---")
                print(f"First-pass TTFT: {first.ttft:.3f} s")
                print(f"Cached TTFT:     {second.ttft:.3f} s")
                print(f"TTFT reduction:  {first.ttft - second.ttft:.3f} s")
                print(f"TTFT speedup:    {first.ttft / second.ttft:.2f}x")

    if args.runs > 1:
        print("\n=== Median summary ===")
        m_first = median_or_none([r.ttft for r in first_results])
        m_decode = median_or_none([r.decode_tps for r in first_results])
        if m_first is not None:
            print(f"Median first-pass TTFT:   {m_first:.3f} s")
        if m_decode is not None:
            print(f"Median decode throughput: {m_decode:.2f} tok/s")
        if cached_results:
            m_cached = median_or_none([r.ttft for r in cached_results])
            if m_cached is not None:
                print(f"Median cached-prefix TTFT: {m_cached:.3f} s")

    print("\n=== Assistant content from first cycle ===")
    print(first_results[0].content or "(no final content)")


if __name__ == "__main__":
    main()
