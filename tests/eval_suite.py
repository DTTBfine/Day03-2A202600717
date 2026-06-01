"""
Evaluation suite for Lab 3 report.

Usage:
    python tests/eval_suite.py          # standalone, full output
    pytest  tests/eval_suite.py -v      # pytest mode, one test per case

Outputs:
- Per-case pass/fail table
- P50/P99 latency, avg tokens, total cost  (Section 3)
- Success rate summary                      (Section 1)
- Chatbot baseline comparison               (Section 5)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import List, Optional

import pytest

sys.path.insert(0, ".")

from test import (
    collect_research_for_destinations,
    create_llm_provider,
    destination_agent,
    intent_agent,
    load_environment,
    normalize_trip_params,
    planning_agent,
)
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker


# ---------------------------------------------------------------------------
# Eval case definitions  (NOT named TestCase — avoids pytest collection warning)
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    id: str
    query: str
    origin: str                   # force-inject origin so pipeline always runs
    expected_keywords: List[str]  # at least one must appear in the answer
    description: str = ""


EVAL_CASES: List[EvalCase] = [
    EvalCase(
        id="TC01",
        query="Lập kế hoạch 3 ngày đi Đà Nẵng từ Hà Nội, ngân sách 5 triệu",
        origin="Hà Nội",
        expected_keywords=["Đà Nẵng", "ngày", "triệu", "ước tính"],
        description="Specific destination, defined origin, budget",
    ),
    EvalCase(
        id="TC02",
        query="Gợi ý chuyến đi biển 2 ngày từ Hà Nội cuối tuần tới",
        origin="Hà Nội",
        expected_keywords=["biển", "ngày 1", "Ngày 1", "khách sạn", "ăn"],
        description="Vague beach theme, short trip",
    ),
    EvalCase(
        id="TC03",
        query="Đi Sapa 4 ngày từ Hà Nội, 2 người, ngân sách 10 triệu",
        origin="Hà Nội",
        expected_keywords=["Sapa", "Sa Pa", "ngày", "triệu"],
        description="Mountain destination, 2 adults",
    ),
    EvalCase(
        id="TC04",
        query="Lập plan 5 ngày đi Phú Quốc từ TP Hồ Chí Minh, budget 20 triệu",
        origin="TP Hồ Chí Minh",
        expected_keywords=["Phú Quốc", "ngày", "triệu", "máy bay"],
        description="Island destination, flight expected",
    ),
    EvalCase(
        id="TC05",
        query="Muốn thăm quan Hội An 2 ngày từ Đà Nẵng",
        origin="Đà Nẵng",
        expected_keywords=["Hội An", "phố cổ", "ngày"],
        description="Cultural destination, same-city origin",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _answer_passes(answer: str, keywords: List[str]) -> bool:
    """Returns True if at least one expected keyword appears in the answer."""
    lower = answer.lower()
    return any(kw.lower() in lower for kw in keywords)


def _chatbot_baseline(llm, query: str) -> str:
    """Direct LLM call with no tools — simulates the plain chatbot baseline."""
    system = (
        "Bạn là chatbot tư vấn du lịch Việt Nam. "
        "Trả lời bằng tiếng Việt, ngắn gọn, thực tế."
    )
    response = llm.generate(query, system_prompt=system)
    tracker.track_request(
        provider=response.get("provider", "unknown"),
        model=getattr(llm, "model_name", "unknown"),
        usage=response.get("usage", {}),
        latency_ms=response.get("latency_ms", 0),
        agent_name="chatbot_baseline",
    )
    return str(response.get("content", "")).strip()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class CaseResult:
    case_id: str
    query: str
    passed: bool
    latency_s: float
    tokens: int
    cost_usd: float
    answer_preview: str
    baseline_passed: bool = False
    error: Optional[str] = None


def run_agent_case(llm, case: EvalCase) -> CaseResult:
    tracker.reset()
    start = time.perf_counter()
    try:
        full_query = case.query if case.origin in case.query else case.query
        params = normalize_trip_params(intent_agent(llm, full_query))
        params["origin"] = params.get("origin") or case.origin
        params["origin_missing"] = False

        destination_options = destination_agent(llm, full_query, params)
        if not destination_options:
            raise ValueError("No destination options returned")
        destination_options = destination_options[:2]  # limit for speed

        destination_research = collect_research_for_destinations(params, destination_options)
        answer = planning_agent(llm, full_query, params, destination_options, destination_research)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.log_event("EVAL_ERROR", {"case_id": case.id, "error": str(exc)})
        return CaseResult(
            case_id=case.id,
            query=case.query,
            passed=False,
            latency_s=round(elapsed, 2),
            tokens=0,
            cost_usd=0.0,
            answer_preview="",
            error=str(exc),
        )

    elapsed = time.perf_counter() - start
    stats = tracker.get_summary_stats()
    passed = _answer_passes(answer, case.expected_keywords)
    logger.log_event("EVAL_CASE", {
        "case_id": case.id,
        "passed": passed,
        "latency_s": round(elapsed, 2),
        "stats": stats,
    })
    return CaseResult(
        case_id=case.id,
        query=case.query,
        passed=passed,
        latency_s=round(elapsed, 2),
        tokens=stats.get("total_tokens", 0),
        cost_usd=stats.get("total_cost_usd", 0.0),
        answer_preview=answer[:200],
    )


def run_baseline_case(llm, case: EvalCase) -> bool:
    tracker.reset()
    try:
        answer = _chatbot_baseline(llm, case.query)
        return _answer_passes(answer, case.expected_keywords)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_environment()
    llm = create_llm_provider()

    print("\n" + "=" * 65)
    print("EVAL SUITE — Travel Planner Agent vs Chatbot Baseline")
    print("=" * 65)

    agent_results: List[CaseResult] = []
    for case in EVAL_CASES:
        print(f"\n[{case.id}] {case.description}")
        print(f"  Query: {case.query[:80]}")
        result = run_agent_case(llm, case)
        result.baseline_passed = run_baseline_case(llm, case)
        agent_results.append(result)
        status = "PASS" if result.passed else "FAIL"
        baseline = "PASS" if result.baseline_passed else "FAIL"
        print(f"  Agent: {status}  |  Baseline: {baseline}  |  {result.latency_s}s  |  {result.tokens} tokens  |  ${result.cost_usd:.5f}")
        if result.error:
            print(f"  Error: {result.error}")

    # ---- Summary ----
    agent_pass = sum(1 for r in agent_results if r.passed)
    baseline_pass = sum(1 for r in agent_results if r.baseline_passed)
    total = len(agent_results)

    all_latencies = sorted(r.latency_s * 1000 for r in agent_results if not r.error)
    n = len(all_latencies)
    p50 = all_latencies[int(n * 0.5)] if n else 0
    p99 = all_latencies[-1] if n else 0
    total_tokens = sum(r.tokens for r in agent_results)
    total_cost = sum(r.cost_usd for r in agent_results)

    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    print(f"  Agent  success rate : {agent_pass}/{total} ({agent_pass/total*100:.0f}%)")
    print(f"  Baseline success rate: {baseline_pass}/{total} ({baseline_pass/total*100:.0f}%)")
    print(f"  P50 latency         : {p50:.0f} ms")
    print(f"  P99 latency         : {p99:.0f} ms")
    print(f"  Total tokens        : {total_tokens}")
    print(f"  Total cost (est.)   : ${total_cost:.5f}")
    print()

    # ---- Ablation table ----
    print("ABLATION: Chatbot vs Agent")
    print(f"  {'ID':<6} {'Chatbot':>10} {'Agent':>10} {'Winner':>10}")
    for r in agent_results:
        b = "PASS" if r.baseline_passed else "FAIL"
        a = "PASS" if r.passed else "FAIL"
        if r.passed and not r.baseline_passed:
            winner = "Agent"
        elif r.baseline_passed and not r.passed:
            winner = "Baseline"
        elif r.passed and r.baseline_passed:
            winner = "Draw"
        else:
            winner = "Both fail"
        print(f"  {r.case_id:<6} {b:>10} {a:>10} {winner:>10}")

    print()


# ---------------------------------------------------------------------------
# pytest entry points — one test per eval case + one overall success-rate test
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def llm():
    load_environment()
    return create_llm_provider()


@pytest.mark.parametrize("case", EVAL_CASES, ids=[c.id for c in EVAL_CASES])
def test_agent_case(llm, case: EvalCase) -> None:
    """Agent must return an answer containing at least one expected keyword."""
    result = run_agent_case(llm, case)
    assert result.passed, (
        f"[{case.id}] No expected keyword found.\n"
        f"Keywords: {case.expected_keywords}\n"
        f"Preview : {result.answer_preview or result.error}"
    )


def test_agent_success_rate(llm) -> None:
    """Overall success rate must reach at least 60% (3/5 cases)."""
    results = [run_agent_case(llm, case) for case in EVAL_CASES]
    passed = sum(1 for r in results if r.passed)
    rate = passed / len(results)
    assert rate >= 0.6, f"Success rate {passed}/{len(results)} ({rate:.0%}) below 60% threshold"


if __name__ == "__main__":
    main()
