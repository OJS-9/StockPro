"""
Research orchestrator for coordinating parallel specialized research agents.
"""

import os
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from research_plan import ResearchPlan
from research_subjects import get_research_subject_by_id
from specialized_agent import SpecializedResearchAgent

# Default maximum worker count – controls how many specialized agents
# run concurrently.  Spreads token usage over time.
DEFAULT_MAX_WORKERS = int(os.getenv("RESEARCH_MAX_WORKERS", "10"))


class ResearchOrchestrator:
    """Orchestrates parallel research across multiple specialized agents."""

    def __init__(self, api_key: str = None):
        """
        Initialize the research orchestrator.

        Args:
            api_key: Kept for interface compatibility; not used (Gemini key comes from env).
        """
        pass

    def run_parallel_research(
        self,
        plan: ResearchPlan,
        max_workers: int = DEFAULT_MAX_WORKERS,
        trace_context=None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Execute parallel research using specialized agents driven by a ResearchPlan.

        Subjects are submitted to the thread pool in priority order
        (plan.selected_subject_ids is already sorted).

        Args:
            plan: ResearchPlan from PlannerAgent
            max_workers: Maximum number of parallel workers

        Returns:
            Dictionary mapping subject_id → research result dict
        """
        ticker = plan.ticker
        trade_type = plan.trade_type
        subject_ids = plan.selected_subject_ids

        print(f"Starting parallel research for {ticker} ({trade_type})...")
        print(
            f"Researching {len(subject_ids)} subjects with up to "
            f"{max_workers} concurrent workers..."
        )

        start_time = time.time()
        results: Dict[str, Dict[str, Any]] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id: Dict[Any, str] = {}

            # Submit futures in priority order so the thread pool schedules
            # higher-priority work first.
            for subject_id in subject_ids:
                try:
                    subject = get_research_subject_by_id(subject_id)
                except ValueError as exc:
                    print(f"⚠  Skipping unknown subject id '{subject_id}': {exc}")
                    continue

                focus_hint = plan.subject_focus.get(subject_id, "")
                agent = SpecializedResearchAgent()
                future = executor.submit(
                    agent.research_subject,
                    ticker,
                    subject,
                    trade_type,
                    focus_hint,
                    trace_context,
                )
                future_to_id[future] = subject_id

            # Collect results as they complete
            completed = 0
            total = len(future_to_id)
            for future in as_completed(future_to_id):
                subject_id = future_to_id[future]
                try:
                    result = future.result()
                    results[subject_id] = result
                    completed += 1
                    subject_name = result.get('subject_name', subject_id)
                    print(
                        f"✓ Completed research for: {subject_name} "
                        f"({completed}/{total})"
                    )
                    if trace_context:
                        trace_context.emit_step(f"Completed: {subject_name}")
                except Exception as e:
                    print(f"✗ Error researching {subject_id}: {e}")
                    results[subject_id] = {
                        "subject_id": subject_id,
                        "subject_name": subject_id,
                        "research_output": f"Error: {str(e)}",
                        "sources": [],
                        "ticker": ticker,
                        "trade_type": trade_type,
                        "focus_hint": plan.subject_focus.get(subject_id, ""),
                        "error": str(e),
                    }
                    completed += 1

        elapsed = time.time() - start_time
        print(f"✓ Parallel research completed in {elapsed:.2f} seconds")

        return results

    def get_research_summary(self, results: Dict[str, Dict[str, Any]]) -> str:
        """
        Generate a summary of research results.

        Args:
            results: Dictionary of research results from parallel execution

        Returns:
            Summary string
        """
        summary_lines = ["Research Summary:"]
        summary_lines.append(f"Total subjects researched: {len(results)}")

        successful = sum(1 for r in results.values() if "error" not in r)
        summary_lines.append(f"Successful: {successful}/{len(results)}")

        if successful < len(results):
            failed = [r["subject_name"] for r in results.values() if "error" in r]
            summary_lines.append(f"Failed subjects: {', '.join(failed)}")

        return "\n".join(summary_lines)
