"""Verify rescue finalization recovers real data when the ReAct loop hits the turn limit."""

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError


def test_rescue_fires_on_recursion_error_with_gathered_data(monkeypatch):
    import agents.specialized_node as sn

    monkeypatch.setattr(sn, "_get_instructions", lambda *a, **k: "INSTRUCTIONS")

    fake_subject = MagicMock()
    fake_subject.id = "company_overview"
    fake_subject.name = "Company Overview"
    fake_subject.description = "d"
    fake_subject.prompt_template = "Research {ticker}"

    monkeypatch.setattr(sn, "get_research_subject_by_id", lambda _s: fake_subject)
    monkeypatch.setattr(sn, "_get_clients", lambda: (None, None))
    monkeypatch.setattr("langchain_tools.create_all_tools", lambda *a, **k: [])

    # FakeLLM: its .invoke() is called by the rescue path.
    class FakeLLM:
        def __init__(self, **_kw):
            self.calls = []

        def invoke(self, messages):
            self.calls.append(messages)
            return AIMessage(content="RESCUED_OUTPUT_WITH_FINDINGS")

    fake_llm_holder = {}

    def make_llm(**kw):
        llm = FakeLLM(**kw)
        fake_llm_holder["llm"] = llm
        return llm

    monkeypatch.setattr(sn, "ChatGoogleGenerativeAI", make_llm)

    # Fake agent: stream yields two ToolMessages then raises GraphRecursionError.
    def fake_create_react_agent(_llm, _tools, *_a, **_kw):
        agent = MagicMock()

        def _stream(_payload, config=None, stream_mode=None):
            yield {
                "messages": [
                    HumanMessage(content="Research AAPL"),
                    ToolMessage(content="Tool 1 data: revenue=$100B", tool_call_id="1"),
                ]
            }
            yield {
                "messages": [
                    HumanMessage(content="Research AAPL"),
                    ToolMessage(content="Tool 1 data: revenue=$100B", tool_call_id="1"),
                    ToolMessage(content="Tool 2 data: EPS=$6", tool_call_id="2"),
                ]
            }
            raise GraphRecursionError("recursion limit hit")

        agent.stream.side_effect = _stream
        return agent

    monkeypatch.setattr(sn, "create_react_agent", fake_create_react_agent)

    plan = MagicMock()
    plan.subject_focus = {"company_overview": ""}
    state = {
        "ticker": "AAPL",
        "trade_type": "Investment",
        "plan": plan,
        "subject_id": "company_overview",
        "emitter": None,
        "effective_max_turns": 4,
        "effective_max_output_tokens": 1000,
    }

    result = sn.specialized_node(state)
    out = result["research_outputs"]["company_overview"]["research_output"]
    assert out == "RESCUED_OUTPUT_WITH_FINDINGS"
    # Rescue must have been invoked with the gathered tool data embedded.
    rescue_calls = fake_llm_holder["llm"].calls
    assert len(rescue_calls) == 1
    rescue_prompt_text = rescue_calls[0][0].content
    assert "revenue=$100B" in rescue_prompt_text
    assert "EPS=$6" in rescue_prompt_text


def test_rescue_fires_on_empty_phrase_output(monkeypatch):
    import agents.specialized_node as sn

    monkeypatch.setattr(sn, "_get_instructions", lambda *a, **k: "I")

    fake_subject = MagicMock()
    fake_subject.id = "x"
    fake_subject.name = "X"
    fake_subject.description = "d"
    fake_subject.prompt_template = "Research {ticker}"

    monkeypatch.setattr(sn, "get_research_subject_by_id", lambda _s: fake_subject)
    monkeypatch.setattr(sn, "_get_clients", lambda: (None, None))
    monkeypatch.setattr("langchain_tools.create_all_tools", lambda *a, **k: [])

    class FakeLLM:
        def invoke(self, _messages):
            return AIMessage(content="REAL FINDINGS")

    monkeypatch.setattr(sn, "ChatGoogleGenerativeAI", lambda **kw: FakeLLM())

    def fake_create_react_agent(_llm, _tools, *_a, **_kw):
        agent = MagicMock()

        def _stream(_payload, config=None, stream_mode=None):
            yield {
                "messages": [
                    ToolMessage(content="Some tool data", tool_call_id="1"),
                    AIMessage(content="Sorry, need more steps to process"),
                ]
            }

        agent.stream.side_effect = _stream
        return agent

    monkeypatch.setattr(sn, "create_react_agent", fake_create_react_agent)

    plan = MagicMock()
    plan.subject_focus = {}
    state = {
        "ticker": "AAPL",
        "trade_type": "Investment",
        "plan": plan,
        "subject_id": "x",
        "emitter": None,
        "effective_max_turns": 4,
        "effective_max_output_tokens": 1000,
    }

    result = sn.specialized_node(state)
    assert result["research_outputs"]["x"]["research_output"] == "REAL FINDINGS"
