"""
SynthesisAgent as a LangGraph node.

Consolidates all specialized research outputs into a final report.
No tools — pure synthesis LLM call.
"""

import os
from typing import Dict, Any, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from research_plan import ResearchPlan
from research_subjects import get_research_subject_by_id

SYNTHESIS_MODEL = os.getenv("SYNTHESIS_AGENT_MODEL", "gemini-2.5-pro")
SYNTHESIS_MAX_OUTPUT_TOKENS = int(os.getenv("SYNTHESIS_AGENT_MAX_OUTPUT_TOKENS", "8000"))

_TRADE_TYPE_FRAMING = {
    "Day Trade": "an actionable intraday/short-term briefing",
    "Swing Trade": "a focused 1–14 day swing trade thesis",
    "Investment": "a comprehensive long-term equity research report",
}


def _get_synthesis_instructions(ticker: str, trade_type: str, plan: ResearchPlan) -> str:
    from date_utils import get_datetime_context_string
    datetime_context = get_datetime_context_string()
    framing = _TRADE_TYPE_FRAMING.get(trade_type, "a research report")
    trade_context_block = (
        f"\n**User's stated goals / context:**\n{plan.trade_context}\n"
        if plan.trade_context
        else ""
    )
    return f"""You are a senior equity research analyst synthesizing specialized research findings into {framing} for {ticker}.

{datetime_context}
{trade_context_block}
**Your Task:**
Integrate research findings from multiple specialized agents into a structured, detailed report.
Your role is to PRESERVE and ORGANIZE all detailed information, NOT to summarize or condense it.

**CRITICAL: Detail Preservation Requirements**
- **PRESERVE ALL SPECIFIC DATA**: Include all metrics, numbers, percentages, dollar amounts, and quantitative data points
- **PRESERVE ALL FACTS**: Include all specific facts, findings, and qualitative insights
- **INTEGRATE, DON'T SUMMARIZE**: Integrate information into a structured format without losing depth
- **MINIMUM DETAIL**: Each major section should include at least 3–5 specific data points or facts
- **CROSS-REFERENCE**: Where information from different subjects relates, make those connections explicit

**Trade Type Framing:** {trade_type} — frame this as {framing}.

**Guidelines:**
- Only use information from the provided research outputs
- Do not add information not present in the research findings
- Cite all sources from the research outputs
- If information is missing for a section, note it clearly
- Ensure the report is comprehensive and fully utilizes all research findings"""


def _build_report_sections(trade_type: str, subject_ids_run: List[str]) -> str:
    subject_names: Dict[str, str] = {}
    subject_descriptions: Dict[str, str] = {}
    for sid in subject_ids_run:
        try:
            s = get_research_subject_by_id(sid)
            subject_names[sid] = s.name
            subject_descriptions[sid] = s.description
        except ValueError:
            subject_names[sid] = sid
            subject_descriptions[sid] = ""

    sections = ["1. **Executive Summary** — Key findings, recommendation, and top metrics"]
    section_num = 2
    for sid in subject_ids_run:
        if sid == "risk_factors":
            continue
        name = subject_names.get(sid, sid)
        desc = subject_descriptions.get(sid, "")
        sections.append(f"{section_num}. **{name}**" + (f" — {desc}" if desc else ""))
        section_num += 1

    if "risk_factors" in subject_ids_run:
        sections.append(
            f"{section_num}. **Risk Factors** — Key risks: operational, financial, regulatory, and macro"
        )
        section_num += 1

    sections.append(
        f"{section_num}. **Key Takeaways** — 5–7 bullets, each with a specific metric or fact; "
        "cover growth, margin, competitive position, near-term catalyst, and primary risk"
    )
    section_num += 1
    sections.append(f"{section_num}. **Sources and Citations** — All sources with proper attribution")
    return "\n".join(sections)


def _build_synthesis_prompt(
    ticker: str,
    trade_type: str,
    research_outputs: Dict[str, Dict[str, Any]],
    plan: ResearchPlan,
) -> str:
    from date_utils import get_datetime_context_string
    datetime_context = get_datetime_context_string()
    framing = _TRADE_TYPE_FRAMING.get(trade_type, "a research report")

    ordered_ids = [sid for sid in plan.selected_subject_ids if sid in research_outputs]
    for sid in research_outputs:
        if sid not in ordered_ids:
            ordered_ids.append(sid)

    sections_text = _build_report_sections(trade_type, ordered_ids)

    prompt_parts = [
        f"**TASK: Synthesize research into {framing} for {ticker} ({trade_type})**",
        "",
        datetime_context,
        "",
    ]

    if plan.trade_context:
        prompt_parts += [
            "**User's stated goals / context (frame the report around this):**",
            plan.trade_context,
            "",
        ]

    prompt_parts += [
        "**CRITICAL INSTRUCTIONS:**",
        "",
        f"Specialized agents have researched {len(ordered_ids)} subjects on {ticker}.",
        "PRESERVE ALL DETAILS — do not summarize away specific numbers, facts, or examples.",
        "",
        "**Report Structure to follow (in this order):**",
        sections_text,
        "",
        "**Research Findings from Specialized Agents:**",
        "",
    ]

    for sid in ordered_ids:
        result = research_outputs[sid]
        subject_name = result.get("subject_name", sid)
        research_output = result.get("research_output", "No research output available")
        focus_hint = result.get("focus_hint", "")
        sources = result.get("sources", [])

        prompt_parts.append(f"### {subject_name}")
        if focus_hint:
            prompt_parts.append(f"*User focus for this section: {focus_hint}*")
        prompt_parts.append("")
        prompt_parts.append(research_output)

        if sources:
            prompt_parts.append("")
            prompt_parts.append("**Sources:**")
            for i, source in enumerate(sources, 1):
                prompt_parts.append(f"{i}. {source}")

        prompt_parts += ["", "---", ""]

    prompt_parts += [
        "",
        "**FINAL INSTRUCTIONS:**",
        "",
        f"Write the {framing} now following the section structure above.",
        "- Preserve ALL specific metrics, numbers, facts, and details from the research outputs.",
        "- Maintain section order exactly as specified.",
        "- Cite all sources.",
        "- Draw connections between sections where relevant.",
        "- The **Key Takeaways** section is REQUIRED. Write 5–7 bullet points.",
        "  Each bullet must contain a specific metric or fact (no vague conclusions).",
        "  Cover at minimum: one growth finding, one margin finding, one competitive finding,",
        "  one near-term catalyst, and one primary risk.",
        "- **COMPLETION REQUIREMENT**: You MUST write every section in the structure above,",
        "  in order, without stopping early. End the report with: END_OF_REPORT",
    ]

    return "\n".join(prompt_parts)


def synthesis_node(state: dict) -> dict:
    """
    LangGraph node: synthesizes all research outputs into a final report.

    Reads: ticker, trade_type, research_outputs, plan, emitter
    Writes: report_text
    """
    ticker = state["ticker"]
    trade_type = state["trade_type"]
    research_outputs = state["research_outputs"]
    plan = state["plan"]
    emitter = state.get("emitter")

    if emitter:
        emitter.emit("Synthesizing report...")

    print(f"[SynthesisNode] Synthesizing {len(research_outputs)} research outputs for {ticker}...")

    synthesis_prompt = _build_synthesis_prompt(ticker, trade_type, research_outputs, plan)
    system_instructions = _get_synthesis_instructions(ticker, trade_type, plan)

    llm = ChatGoogleGenerativeAI(
        model=SYNTHESIS_MODEL,
        temperature=0.7,
        max_output_tokens=SYNTHESIS_MAX_OUTPUT_TOKENS,
    )

    try:
        response = llm.invoke(
            [SystemMessage(content=system_instructions), HumanMessage(content=synthesis_prompt)]
        )
        report_text = response.content or ""
        print(f"[SynthesisNode] Report: {len(report_text)} chars")
        return {"report_text": report_text}
    except Exception as e:
        error_msg = f"Error synthesizing report: {e}"
        print(error_msg)
        return {"report_text": error_msg}
