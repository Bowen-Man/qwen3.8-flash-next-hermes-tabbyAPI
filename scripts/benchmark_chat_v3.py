"""Benchmark a local TabbyAPI / OpenAI-compatible chat endpoint.

Examples
--------
Short baseline:
    python benchmark_chat.py

Approx. 8K / 32K / 64K prompt targets:
    python benchmark_chat.py --prompt-tokens 8000
    python benchmark_chat.py --prompt-tokens 32000
    python benchmark_chat.py --prompt-tokens 64000

Test repeated-prefix / KV-cache reuse:
    python benchmark_chat.py --prompt-tokens 32000 --cache-reuse

Notes
-----
- --prompt-tokens targets the *server-reported chat prompt token count*.
- The script performs two small calibration requests to estimate how many filler
  repetitions are needed for the requested target.
- The final benchmark always prints the actual prompt_tokens returned by the server.
- A unique nonce is inserted into normal benchmark prompts to avoid accidental
  prefix-cache reuse across separate runs.
"""

from __future__ import annotations

import argparse
import os
import time
import uuid
from dataclasses import dataclass

from openai import OpenAI


DEFAULT_BASE_URL = os.getenv("TABBY_BASE_URL", "http://127.0.0.1:8088/v1")
DEFAULT_MODEL = os.getenv(
    "TABBY_MODEL",
    "Qwen3.8-Flash-Next-exl3-3.05bpw",
)

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark a local TabbyAPI/OpenAI-compatible chat endpoint."
    )
    parser.add_argument(
        "--prompt-tokens",
        type=int,
        default=None,
        help=(
            "Target total server-reported prompt tokens. "
            "Examples: 8000, 16000, 32000, 64000."
        ),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Maximum completion tokens (default: 256).",
    )
    parser.add_argument(
        "--cache-reuse",
        action="store_true",
        help=(
            "Run the exact same long prompt twice and report both results. "
            "Useful for testing prefix/KV-cache reuse."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"OpenAI-compatible base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model ID (default: {DEFAULT_MODEL}).",
    )
    return parser.parse_args()


def one_token_probe(client: OpenAI, model: str, prompt: str) -> int:
    """Return server-reported prompt token count for a tiny calibration request.

    TabbyAPI may return usage only on streamed responses, so calibration uses
    stream=True with stream_options={"include_usage": True}.
    """
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
            "Your TabbyAPI build may not expose prompt token usage for this request."
        )

    return usage.prompt_tokens


def calibration_prompt(repeats: int) -> str:
    nonce = uuid.uuid4().hex
    return (
        f"Calibration nonce: {nonce}\n"
        "Ignore the following filler. This request only measures tokenization.\n"
        + (FILLER_UNIT * repeats)
        + QUESTION
    )


def estimate_repetitions(
    client: OpenAI,
    model: str,
    target_tokens: int,
) -> tuple[int, float, float]:
    """Estimate filler repetitions needed to approach target prompt tokens."""
    small_repeats = 256
    large_repeats = 1024

    small_tokens = one_token_probe(
        client,
        model,
        calibration_prompt(small_repeats),
    )
    large_tokens = one_token_probe(
        client,
        model,
        calibration_prompt(large_repeats),
    )

    tokens_per_repeat = (
        (large_tokens - small_tokens)
        / (large_repeats - small_repeats)
    )

    if tokens_per_repeat <= 0:
        raise RuntimeError("Calibration produced an invalid token/repetition estimate.")

    overhead = small_tokens - small_repeats * tokens_per_repeat
    repetitions = round((target_tokens - overhead) / tokens_per_repeat)
    repetitions = max(repetitions, 1)

    return repetitions, tokens_per_repeat, overhead


def build_long_prompt(repetitions: int, nonce: str) -> str:
    return (
        f"Benchmark nonce: {nonce}\n"
        "The following text is synthetic benchmark context. "
        "Do not summarize it; use it only to create a long context window.\n\n"
        + (FILLER_UNIT * repetitions)
        + QUESTION
    )


def run_stream(
    client: OpenAI,
    model: str,
    prompt: str,
    max_tokens: int,
    label: str,
) -> Result:
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


def print_result(result: Result, requested_tokens: int | None) -> None:
    print(f"\n=== {result.label} ===")

    if requested_tokens is not None:
        print(f"Requested prompt target: {requested_tokens:,} tokens")

    if result.prompt_tokens is not None:
        print(f"Actual prompt tokens:     {result.prompt_tokens:,}")

        if requested_tokens:
            error = result.prompt_tokens - requested_tokens
            error_pct = 100 * error / requested_tokens
            print(
                f"Target error:             {error:+,} tokens "
                f"({error_pct:+.2f}%)"
            )

    if result.ttft is not None:
        print(f"TTFT:                     {result.ttft:.3f} s")
    else:
        print("TTFT:                     n/a")

    print(f"Total time:               {result.total_time:.3f} s")
    print(f"Generated characters:     {result.generated_chars:,}")

    decode_time = None
    if result.ttft is not None:
        decode_time = result.total_time - result.ttft

    if decode_time and decode_time > 0:
        print(
            "Generated characters/sec: "
            f"{result.generated_chars / decode_time:.1f}"
        )

    if result.completion_tokens is not None:
        print(f"Completion tokens:        {result.completion_tokens:,}")

    if result.total_tokens is not None:
        print(f"Total tokens:             {result.total_tokens:,}")

    if decode_time and decode_time > 0 and result.completion_tokens:
        print(
            "Approx. decode throughput: "
            f"{result.completion_tokens / decode_time:.2f} tok/s"
        )

    if result.ttft and result.ttft > 0 and result.prompt_tokens:
        print(
            "Approx. prompt/TTFT rate:   "
            f"{result.prompt_tokens / result.ttft:.1f} tok/s"
        )


def main() -> None:
    args = parse_args()

    if args.prompt_tokens is not None and args.prompt_tokens < 256:
        raise SystemExit("--prompt-tokens must be at least 256.")

    client = OpenAI(
        base_url=args.base_url,
        api_key="local",
    )

    print(f"Base URL: {args.base_url}")
    print(f"Model: {args.model}")
    print(f"Max output tokens: {args.max_tokens}")

    if args.prompt_tokens is None:
        prompt = SHORT_PROMPT
        requested_tokens = None
    else:
        if args.prompt_tokens + args.max_tokens > 81920:
            print(
                "WARNING: requested prompt + max output exceeds 81,920 tokens. "
                "This may fail with the repository's baseline server configuration."
            )

        print(f"Requested prompt target: {args.prompt_tokens:,} tokens")
        print("Calibrating against server-reported token usage...")

        repetitions, tokens_per_repeat, overhead = estimate_repetitions(
            client,
            args.model,
            args.prompt_tokens,
        )

        print(f"Estimated tokens/filler unit: {tokens_per_repeat:.3f}")
        print(f"Estimated chat/template overhead: {overhead:.1f} tokens")
        print(f"Filler repetitions: {repetitions:,}")

        nonce = uuid.uuid4().hex
        prompt = build_long_prompt(repetitions, nonce)
        requested_tokens = args.prompt_tokens

    first = run_stream(
        client,
        args.model,
        prompt,
        args.max_tokens,
        "Run 1",
    )
    print_result(first, requested_tokens)

    if args.cache_reuse:
        if args.prompt_tokens is None:
            print(
                "\nNOTE: --cache-reuse is most informative together with "
                "--prompt-tokens for long-context testing."
            )

        second = run_stream(
            client,
            args.model,
            prompt,
            args.max_tokens,
            "Run 2 — same exact prompt (cache-reuse test)",
        )
        print_result(second, requested_tokens)

        if first.ttft and second.ttft:
            delta = first.ttft - second.ttft
            speedup = first.ttft / second.ttft
            print("\n=== Cache reuse comparison ===")
            print(f"Run 1 TTFT: {first.ttft:.3f} s")
            print(f"Run 2 TTFT: {second.ttft:.3f} s")
            print(f"TTFT reduction: {delta:.3f} s")
            print(f"TTFT speedup: {speedup:.2f}x")

    print("\n=== Assistant content ===")
    print(first.content or "(no final content)")


if __name__ == "__main__":
    main()
