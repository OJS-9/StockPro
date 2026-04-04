"""
SynthesisAgent as a LangGraph node.

Consolidates all specialized research outputs into a final report.
No tools — pure synthesis LLM call.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from langsmith_service import StepEmitter, synthesis_invoke_config
from report_quality import assess_report_structure
from research_plan import ResearchPlan
from research_subjects import get_research_subject_by_id

logger = logging.getLogger(__name__)

SYNTHESIS_MODEL = os.getenv("SYNTHESIS_AGENT_MODEL", "gemini-2.5-pro")
SYNTHESIS_MAX_OUTPUT_TOKENS = int(
    os.getenv("SYNTHESIS_AGENT_MAX_OUTPUT_TOKENS", "8000")
)

_END_MARKER = "END_OF_REPORT"
# Rough chars-per-token for Gemini (~4). If output >= 90% of the token limit, assume truncation.
_TRUNCATION_THRESHOLD = 0.9


def _log_structure_quality(
    report_text: str, emitter: Optional[StepEmitter] = None
) -> None:
    """Log when Markdown section headings look incomplete (Phase 1.7 quality signal)."""
    if not report_text or report_text.startswith("[INCOMPLETE REPORT"):
        return
    if report_text.strip().startswith("Error synthesizing report:"):
        return
    ok, missing = assess_report_structure(report_text)
    if not ok:
        logger.warning(
            "Report structure quality: Markdown headings missing expected topics: %s",
            ", ".join(missing),
            extra={
                "quality_pass": False,
                "quality_missing_sections": ",".join(missing),
            },
        )
        if emitter:
            emitter.emit(
                "Review: report may be missing standard sections ("
                + ", ".join(missing)
                + ")."
            )


def _is_truncated(text: str, max_tokens: int) -> bool:
    """Return True if END_OF_REPORT is missing AND output length suggests the model hit its limit."""
    if _END_MARKER in text:
        return False
    return (len(text) / 4) >= max_tokens * _TRUNCATION_THRESHOLD


_TRADE_TYPE_FRAMING = {
    "Day Trade": "an actionable intraday/short-term briefing",
    "Swing Trade": "a focused 1–14 day swing trade thesis",
    "Investment": "a comprehensive long-term equity research report",
}


def _get_synthesis_instructions(
    ticker: str, trade_type: str, plan: ResearchPlan
) -> str:
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

    sections = [
        "1. **Executive Summary** — Key findings, recommendation, and top metrics"
    ]
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
    sections.append(
        f"{section_num}. **Sources and Citations** — All sources with proper attribution"
    )
    return "\n".join(sections)


def _build_synthesis_prompt(
    ticker: str,
    trade_type: str,
    research_outputs: Dict[str, Dict[str, Any]],
    plan: ResearchPlan,
    failed_subjects: List[str] = None,
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

    if failed_subjects:
        failed_names = []
        for sid in failed_subjects:
            try:
                failed_names.append(get_research_subject_by_id(sid).name)
            except ValueError:
                failed_names.append(sid)
        prompt_parts += [
            "**NOTE — Missing Research Sections:**",
            f"The following subjects failed to complete and have NO data: {', '.join(failed_names)}.",
            "For these sections, explicitly state 'Research unavailable for this section' — do not fabricate data.",
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
    if progress_fn := state.get("progress_fn"):
        progress_fn(80, "Synthesizing report...")

    logger.info(
        "Synthesizing %s research outputs for %s...",
        len(research_outputs),
        ticker,
    )

    failed_subjects = state.get("failed_subjects", [])
    synthesis_prompt = _build_synthesis_prompt(
        ticker, trade_type, research_outputs, plan, failed_subjects
    )
    system_instructions = _get_synthesis_instructions(ticker, trade_type, plan)

    llm = ChatGoogleGenerativeAI(
        model=SYNTHESIS_MODEL,
        temperature=0.7,
        max_output_tokens=SYNTHESIS_MAX_OUTPUT_TOKENS,
    )

    _ls_config = synthesis_invoke_config(ticker, trade_type)

    total_input_tok = 0
    total_output_tok = 0

    def _extract_usage(resp) -> tuple:
        usage = getattr(resp, "usage_metadata", None) or {}
        return usage.get("input_tokens", 0), usage.get("output_tokens", 0)

    try:
        response = llm.invoke(
            [
                SystemMessage(content=system_instructions),
                HumanMessage(content=synthesis_prompt),
            ],
            config=_ls_config,
        )
        i, o = _extract_usage(response)
        total_input_tok += i
        total_output_tok += o

        report_text = response.content or ""
        logger.info("Report: %s chars, %s/%s tokens", len(report_text), i, o)

        if _END_MARKER not in report_text:
            if _is_truncated(report_text, SYNTHESIS_MAX_OUTPUT_TOKENS):
                logger.warning(
                    "Truncation detected — retrying with continuation prompt"
                )
                retry_response = llm.invoke(
                    [
                        SystemMessage(content=system_instructions),
                        HumanMessage(content=synthesis_prompt),
                        AIMessage(content=report_text),
                        HumanMessage(
                            content=(
                                "The previous response was cut off. Continue the report from where it stopped. "
                                "Complete all remaining sections and end with: END_OF_REPORT"
                            )
                        ),
                    ],
                    config=_ls_config,
                )
                ri, ro = _extract_usage(retry_response)
                total_input_tok += ri
                total_output_tok += ro

                combined = report_text + "\n" + (retry_response.content or "")
                if _END_MARKER in combined:
                    logger.info("Continuation successful: %s chars", len(combined))
                    _log_structure_quality(combined, emitter)
                    return {
                        "report_text": combined,
                        "actual_input_tokens": total_input_tok,
                        "actual_output_tokens": total_output_tok,
                    }
                else:
                    logger.warning(
                        "Continuation did not complete report — flagging as incomplete"
                    )
                    return {
                        "report_text": "[INCOMPLETE REPORT — synthesis was truncated]\n\n"
                        + report_text,
                        "is_partial_report": True,
                        "actual_input_tokens": total_input_tok,
                        "actual_output_tokens": total_output_tok,
                    }
            else:
                logger.info(
                    "END_OF_REPORT absent but output is short (%s chars) — proceeding",
                    len(report_text),
                )

        _log_structure_quality(report_text, emitter)
        return {
            "report_text": report_text,
            "actual_input_tokens": total_input_tok,
            "actual_output_tokens": total_output_tok,
        }
    except Exception as e:
        error_msg = f"Error synthesizing report: {e}"
        logger.exception("Synthesis failed")
        return {
            "report_text": error_msg,
            "is_partial_report": True,
            "actual_input_tokens": total_input_tok,
            "actual_output_tokens": total_output_tok,
        }
