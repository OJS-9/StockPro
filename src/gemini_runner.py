"""
Synchronous multi-turn agent loop using the Google GenAI SDK.
Replaces the openai-agents Runner for all agent execution.
"""

import os
from typing import Optional
from dotenv import load_dotenv

from google import genai
from google.genai import types

load_dotenv()

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Return the shared genai.Client, initializing it on first call."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required. Set it in your .env file.")
        _client = genai.Client(api_key=api_key)
    return _client


def run_agent(
    model: str,
    system_instruction: str,
    tools: list,
    tool_handlers: dict,
    messages: list,
    max_turns: int,
    temperature: float,
    max_output_tokens: int,
    thinking_budget: Optional[int] = None,
) -> str:
    """
    Run a synchronous multi-turn agent loop with optional tool calling.

    Args:
        model: Gemini model ID (e.g. "gemini-2.0-flash")
        system_instruction: System prompt for the agent
        tools: List of types.Tool objects (pass [] for no tools)
        tool_handlers: Dict mapping tool_name -> callable(args_dict) -> str
        messages: List of types.Content objects (conversation so far)
        max_turns: Maximum number of model turns before returning
        temperature: Sampling temperature
        max_output_tokens: Max tokens in model response

    Returns:
        Final text response from the model
    """
    client = _get_client()
    contents = list(messages)
    last_response_text = ""

    thinking_cfg = (
        types.ThinkingConfig(thinking_budget=thinking_budget)
        if thinking_budget is not None
        else None
    )
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools if tools else None,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking_config=thinking_cfg,
    )

    for _ in range(max_turns):
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        contents.append(candidate.content)

        # Collect function calls from this turn
        fn_calls = [p for p in candidate.content.parts if p.function_call]

        if not fn_calls:
            # No tool calls — extract text and return
            text_parts = [p.text for p in candidate.content.parts if hasattr(p, "text") and p.text]
            return "\n".join(text_parts) if text_parts else (response.text or "")

        # Execute each tool and collect responses
        fn_response_parts = []
        for part in fn_calls:
            fc = part.function_call
            handler = tool_handlers.get(fc.name)
            if handler:
                try:
                    result = handler(dict(fc.args))
                except Exception as e:
                    result = f"Tool execution error: {e}"
            else:
                result = f"Unknown tool: {fc.name}"

            fn_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result},
                )
            )

        contents.append(types.Content(role="user", parts=fn_response_parts))

        # Save last text for fallback if max_turns is reached mid-tool-loop
        text_parts = [p.text for p in candidate.content.parts if hasattr(p, "text") and p.text]
        last_response_text = "\n".join(text_parts) if text_parts else ""

    return last_response_text
