"""Verify structured OpenAI tool calling from a local endpoint."""

import argparse
import json
import os
import sys

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment]


DEFAULT_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8088/v1")
DEFAULT_MODEL = os.getenv("LOCAL_LLM_MODEL", "Qwen3.8-Flash-Next-exl3-3.05bpw")
DEFAULT_API_KEY = os.getenv("LOCAL_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "local"))


def parse_args():
    p = argparse.ArgumentParser(description="Test structured OpenAI tool calling.")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--api-key", default=DEFAULT_API_KEY)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if OpenAI is None:
        print("Missing dependency: openai. Install it with: pip install openai")
        return 2
    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    tools = [{
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current time.",
            "parameters": {"type": "object", "properties": {}},
        },
    }]

    response = client.chat.completions.create(
        model=args.model,
        messages=[{"role": "user", "content": "You must call the get_time tool."}],
        tools=tools,
        max_tokens=256,
    )

    choice = response.choices[0]
    message = choice.message
    reasoning = getattr(message, "reasoning_content", None)

    print(f"Base URL: {args.base_url}")
    print(f"Model: {response.model}")
    print(f"Finish reason: {choice.finish_reason}")
    print(f"Reasoning: {reasoning}")
    print(f"Content: {message.content}")
    print(f"Tool calls: {message.tool_calls}")

    if choice.finish_reason != "tool_calls" or not message.tool_calls:
        print("\nFAIL: No structured tool call was returned.")
        return 1

    tool_call = message.tool_calls[0]
    if tool_call.function.name != "get_time":
        print(f"\nFAIL: Expected get_time, got {tool_call.function.name!r}.")
        return 1

    try:
        parsed_args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError as exc:
        print(f"\nFAIL: Tool arguments are not valid JSON: {exc}")
        return 1

    if not isinstance(parsed_args, dict):
        print("\nFAIL: Tool arguments must decode to a JSON object.")
        return 1

    print("\nPASS: Structured tool calling works.")
    print(f"Tool name: {tool_call.function.name}")
    print(f"Arguments: {tool_call.function.arguments}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
