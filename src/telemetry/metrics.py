import statistics
from typing import Any, Dict, List

from src.telemetry.logger import logger

# USD per 1K tokens (input, output)
_PRICE_TABLE: Dict[str, Dict[str, float]] = {
    "gpt-4o":               {"input": 0.0025,   "output": 0.010},
    "gpt-4o-mini":          {"input": 0.00015,  "output": 0.0006},
    "gpt-4-turbo":          {"input": 0.010,    "output": 0.030},
    "gpt-3.5-turbo":        {"input": 0.0005,   "output": 0.0015},
    "gemini-1.5-flash":     {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-pro":       {"input": 0.00125,  "output": 0.005},
    "gemini-2.0-flash":     {"input": 0.0001,   "output": 0.0004},
    "gemini-2.0-flash-exp": {"input": 0.0001,   "output": 0.0004},
}

_FALLBACK_COST_PER_1K = 0.002


class PerformanceTracker:
    """
    Tracking industry-standard metrics for LLMs.
    Collects per-request data and provides session-level aggregations.
    """

    def __init__(self) -> None:
        self.session_metrics: List[Dict[str, Any]] = []

    def track_request(
        self,
        provider: str,
        model: str,
        usage: Dict[str, int],
        latency_ms: int,
        agent_name: str = "unknown",
    ) -> None:
        """Records one LLM call to the session and emits a telemetry event."""
        cost = self._calculate_cost(model, usage)
        metric: Dict[str, Any] = {
    Tracking industry-standard metrics for LLMs and API tools.
    """
    def __init__(self):
        self.session_metrics = []
        self.api_tool_metrics = []
        self.validation_metrics = []

    def track_request(self, provider: str, model: str, usage: Dict[str, int], latency_ms: int):
        """
        Logs a single request metric to our telemetry.
        """
        metric = {
            "provider": provider,
            "model": model,
            "agent": agent_name,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "latency_ms": latency_ms,
            "cost_usd": cost,
            "cost_estimate": self._calculate_cost(model, usage)
        }
        self.session_metrics.append(metric)
        logger.log_event("LLM_METRIC", metric)

    def track_api_tool(self, tool_name: str, destination: str, latency_ms: int,
                       success: bool, error: str = None):
        """Track API tool call metrics."""
        metric = {
            "tool_name": tool_name,
            "destination": destination,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
        }
        self.api_tool_metrics.append(metric)
        logger.log_api_tool(tool_name, destination, latency_ms, success, error)

    def track_validation(self, is_valid: bool, missing_fields: List[str],
                        assumptions: List[str]):
        """Track validation metrics."""
        metric = {
            "is_valid": is_valid,
            "missing_fields": missing_fields,
            "assumptions_count": len(assumptions),
            "validation_missing_fields_count": len(missing_fields),
        }
        self.validation_metrics.append(metric)
        logger.log_event("VALIDATION_METRIC", metric)

    def track_async_research(self, destinations: List[str], total_latency_ms: int,
                             tool_results: List[Dict]):
        """Track async research metrics."""
        total_tools = 0
        failed_tools = 0
        for result in tool_results:
            tools_in_result = result.get("tool_results", {})
            total_tools += len(tools_in_result)
            for key, value in tools_in_result.items():
                if isinstance(value, dict) and value.get("status") == "error":
                    failed_tools += 1

        metric = {
            "destinations_count": len(destinations),
            "total_research_latency_ms": total_latency_ms,
            "total_tools_called": total_tools,
            "api_tool_success_count": total_tools - failed_tools,
            "api_tool_failure_count": failed_tools,
        }
        logger.log_async_research(destinations, total_latency_ms, total_tools, failed_tools)
        return metric

    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        pricing = _PRICE_TABLE.get(model)
        if not pricing:
            return (usage.get("total_tokens", 0) / 1000) * _FALLBACK_COST_PER_1K
        prompt_cost = (usage.get("prompt_tokens", 0) / 1000) * pricing["input"]
        completion_cost = (usage.get("completion_tokens", 0) / 1000) * pricing["output"]
        return round(prompt_cost + completion_cost, 8)

    def get_summary_stats(self) -> Dict[str, Any]:
        """Returns P50, P99, avg latency, avg tokens, and total cost for the session."""
        if not self.session_metrics:
            return {"call_count": 0}

        latencies = sorted(m["latency_ms"] for m in self.session_metrics)
        n = len(latencies)
        total_tokens = sum(m["total_tokens"] for m in self.session_metrics)
        total_cost = sum(m["cost_usd"] for m in self.session_metrics)

        def percentile(sorted_list: List[int], pct: float) -> int:
            idx = max(0, int(len(sorted_list) * pct / 100) - 1)
            return sorted_list[idx]

        return {
            "call_count": n,
            "p50_latency_ms": percentile(latencies, 50),
            "p99_latency_ms": percentile(latencies, 99),
            "avg_latency_ms": round(statistics.mean(latencies)),
            "total_tokens": total_tokens,
            "avg_tokens_per_call": round(total_tokens / n),
            "total_cost_usd": round(total_cost, 6),
        }

    def reset(self) -> None:
        """Clears session metrics (call at the start of each test run)."""
        self.session_metrics.clear()


    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics for the session."""
        return {
            "llm_requests": len(self.session_metrics),
            "total_tokens": sum(m["total_tokens"] for m in self.session_metrics),
            "api_tool_calls": len(self.api_tool_metrics),
            "api_tool_success_count": sum(1 for m in self.api_tool_metrics if m["success"]),
            "api_tool_failure_count": sum(1 for m in self.api_tool_metrics if not m["success"]),
            "validations": len(self.validation_metrics),
            "valid_inputs": sum(1 for m in self.validation_metrics if m["is_valid"]),
            "invalid_inputs": sum(1 for m in self.validation_metrics if not m["is_valid"]),
        }

# Global tracker instance
tracker = PerformanceTracker()
