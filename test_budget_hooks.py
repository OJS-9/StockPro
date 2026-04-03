from unittest.mock import MagicMock
from langchain_core.messages import AIMessage


def test_fan_out_includes_effective_caps():
    """_fan_out passes planner-populated budget fields through to each specialized_node Send."""
    import research_graph as rg

    plan = MagicMock()
    plan.selected_subject_ids = ["news_catalysts", "company_overview"]

    state = {
        "ticker": "AAPL",
        "trade_type": "Investment",
        "conversation_context": "",
        "plan": plan,
        "subject_id": "",
        "research_outputs": {},
        "failed_subjects": [],
        "is_partial_report": False,
        "report_text": "",
        "report_id": "",
        "user_id": None,
        "emitter": None,
        "user_selected_subjects": None,
        "spend_budget_usd": 1.0,
        "estimated_spend_usd": 0.42,
        "effective_max_turns": 3,
        "effective_max_output_tokens": 1234,
        "budget_exhausted": False,
    }

    sends = rg._fan_out(state)
    assert len(sends) == 2
    for send in sends:
        assert send.node == "specialized_node"
        assert send.arg["effective_max_turns"] == 3
        assert send.arg["effective_max_output_tokens"] == 1234
        assert send.arg["estimated_spend_usd"] == 0.42
        assert send.arg["budget_exhausted"] is False


def test_specialized_node_uses_effective_caps(monkeypatch):
    import agents.specialized_node as sn

    # Stub instruction builder to avoid datetime context dependencies.
    monkeypatch.setattr(sn, "_get_instructions", lambda *_args, **_kwargs: "INSTRUCTIONS")

    fake_subject = MagicMock()
    fake_subject.id = "company_overview"
    fake_subject.name = "Company Overview"
    fake_subject.description = "Some description"
    fake_subject.prompt_template = "Research {ticker}"

    monkeypatch.setattr(sn, "get_research_subject_by_id", lambda _sid: fake_subject)
    monkeypatch.setattr(sn, "_get_clients", lambda: (None, None))
    monkeypatch.setattr("langchain_tools.create_all_tools", lambda *_args, **_kwargs: [])

    captured = {"max_output_tokens": None, "recursion_limit": None}

    class FakeLLM:
        def __init__(self, **kwargs):
            captured["max_output_tokens"] = kwargs.get("max_output_tokens")

    def fake_create_react_agent(_llm, _tools, *args, **kwargs):
        agent = MagicMock()

        def _invoke(_payload, config=None):
            captured["recursion_limit"] = (config or {}).get("recursion_limit")
            fake_msg = AIMessage(content="OUTPUT")
            return {"messages": [fake_msg]}

        agent.invoke.side_effect = _invoke
        return agent

    monkeypatch.setattr(sn, "ChatGoogleGenerativeAI", lambda **kwargs: FakeLLM(**kwargs))
    monkeypatch.setattr(sn, "create_react_agent", fake_create_react_agent)

    plan = MagicMock()
    plan.subject_focus = {"company_overview": "focus hint"}
    state = {
        "ticker": "AAPL",
        "trade_type": "Investment",
        "plan": plan,
        "subject_id": "company_overview",
        "emitter": None,
        "effective_max_turns": 5,
        "effective_max_output_tokens": 777,
    }

    result = sn.specialized_node(state)
    assert result["research_outputs"]["company_overview"]["research_output"] == "OUTPUT"
    assert captured["max_output_tokens"] == 777
    assert captured["recursion_limit"] == 10, "recursion_limit should be effective_max_turns * 2"

