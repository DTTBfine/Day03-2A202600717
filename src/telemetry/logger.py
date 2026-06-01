import logging
import json
import os
from datetime import datetime
from typing import Any, Dict

class IndustryLogger:
    """
    Structured logger that simulates industry practices.
    Logs to both console and a file in JSON format.
    """
    def __init__(self, name: str = "AI-Lab-Agent", log_dir: str = "logs"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # File Handler (JSON)
        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
        file_handler = logging.FileHandler(log_file)

        # Console Handler
        console_handler = logging.StreamHandler()

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def log_event(self, event_type: str, data: Dict[str, Any]):
        """Logs an event with a timestamp and type."""
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event_type,
            "data": data
        }
        self.logger.info(json.dumps(payload))

    def log_validation(self, validation_result: Dict[str, Any], user_message: str):
        """Log validation result for travel input."""
        self.log_event("VALIDATION_RESULT", {
            "user_message": user_message,
            "is_valid": validation_result.get("is_valid", False),
            "missing_fields": validation_result.get("missing_fields", []),
            "assumptions": validation_result.get("assumptions", []),
            "normalized_input": validation_result.get("normalized_input", {}),
        })

    def log_api_tool(self, tool_name: str, destination: str, latency_ms: int,
                     success: bool, error: str = None):
        """Log API tool call with latency and success/failure."""
        self.log_event("API_TOOL_CALL", {
            "tool_name": tool_name,
            "destination": destination,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
        })

    def log_async_research(self, destinations: list, total_latency_ms: int,
                           total_tools: int, failed_tools: int):
        """Log async research completion."""
        self.log_event("ASYNC_RESEARCH_COMPLETE", {
            "destinations": destinations,
            "total_latency_ms": total_latency_ms,
            "total_tools_called": total_tools,
            "failed_tools": failed_tools,
        })

    def info(self, msg: str):
        self.logger.info(msg)

    def error(self, msg: str, exc_info=True):
        self.logger.error(msg, exc_info=exc_info)

# Global logger instance
logger = IndustryLogger()
