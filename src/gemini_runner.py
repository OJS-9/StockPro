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


def _contents_to_log(contents: list) -> list:
    """Serialize types.Content objects to a JSON-safe list for LangFuse."""
    result = []
    for c in contents:
        parts_text = []
        for p in (c.parts or []):
            text = getattr(p, "text", None)
            if text:
                parts_text.append(text)
            else:
                fc = getattr(p, "function_call", None)
                if fc:
                    parts_text.append(f"[tool_call: {fc.name}({dict(fc.args)})]")
                else:
                    fr = getattr(p, "function_response", None)
                    if fr:
                        parts_text.append(f"[tool_result: {fr.name}]")
        result.append({"role": c.role, "content": "\n".join(parts_text)})
    return result


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
    check_end_marker: bool = False,
    trace_context=None,
    parent_span=None,
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

    for turn in range(max_turns):
        gen = None
        if trace_context:
            gen = trace_context.start_generation(
                name=f"llm:turn-{turn + 1}",
                model=model,
                input={"system": system_instruction, "messages": _contents_to_log(contents)},
                parent_span=parent_span,
            )

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        if not response.candidates:
            # Empty or blocked response — return last text or fallback
            fallback = getattr(response, "text", None) or ""
            return fallback if fallback else last_response_text or "[No response from model]"

        candidate = response.candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        finish_message = getattr(candidate, "finish_message", None)
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", "?")
        output_tokens = getattr(usage, "candidates_token_count", "?")
        print(
            f"[Gemini] finish_reason={finish_reason}, finish_message={finish_message}, "
            f"prompt_tokens={prompt_tokens}, output_tokens={output_tokens}, "
            f"max_output_tokens={max_output_tokens}"
        )

        contents.append(candidate.content)

        # Collect function calls from this turn
        fn_calls = [p for p in candidate.content.parts if p.function_call]

        if not fn_calls:
            # No tool calls — extract text and return
            text_parts = [p.text for p in candidate.content.parts if hasattr(p, "text") and p.text]
            final_text = "\n".join(text_parts) if text_parts else (getattr(response, "text", None) or "")
            if finish_reason and getattr(finish_reason, "value", finish_reason) == "MAX_TOKENS":
                print(f"[Gemini] WARNING: response truncated by MAX_TOKENS limit ({max_output_tokens})")
            elif check_end_marker and final_text and "END_OF_REPORT" not in final_text and output_tokens > 1000:
                print(f"[Gemini] WARNING: END_OF_REPORT marker missing — model may have stopped early (output_tokens={output_tokens})")
            if trace_context and gen:
                trace_context.end_generation(
                    gen, output=final_text, usage=getattr(response, "usage_metadata", None)
                )
            return final_text

        # Log tool calls to generation span then end it
        if trace_context and gen:
            tool_calls_log = [
                {"tool_call": p.function_call.name, "args": dict(p.function_call.args)}
                for p in fn_calls
            ]
            trace_context.end_generation(
                gen, output=tool_calls_log, usage=getattr(response, "usage_metadata", None)
            )

        # Execute each tool and collect responses
        fn_response_parts = []
        for part in fn_calls:
            fc = part.function_call
            tool_span = None
            if trace_context:
                tool_span = trace_context.start_child_span(
                    name=f"tool:{fc.name}",
                    input={"tool": fc.name, "args": dict(fc.args)},
                    parent_span=parent_span,
                )
            handler = tool_handlers.get(fc.name)
            if handler:
                try:
                    result = handler(dict(fc.args))
                except Exception as e:
                    result = f"Tool execution error: {e}"
            else:
                result = f"Unknown tool: {fc.name}"

            if trace_context:
                trace_context.end_span(tool_span, output=result)

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
