from openai import OpenAI


BASE_URL = "http://127.0.0.1:8088/v1"
MODEL = "Qwen3.8-Flash-Next-exl3-3.05bpw"


client = OpenAI(
    base_url=BASE_URL,
    api_key="local",  # TabbyAPI auth is disabled in the example config
)


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current time.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }
]


response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "user",
            "content": "You must call the get_time tool.",
        }
    ],
    tools=tools,
    max_tokens=256,
)


choice = response.choices[0]
message = choice.message


print(f"Model: {response.model}")
print(f"Finish reason: {choice.finish_reason}")
print(f"Reasoning: {message.reasoning_content}")
print(f"Content: {message.content}")
print(f"Tool calls: {message.tool_calls}")


if choice.finish_reason == "tool_calls" and message.tool_calls:
    tool_call = message.tool_calls[0]

    print("\nPASS: Structured tool calling works.")
    print(f"Tool name: {tool_call.function.name}")
    print(f"Arguments: {tool_call.function.arguments}")
else:
    print("\nFAIL: No structured tool call was returned.")
