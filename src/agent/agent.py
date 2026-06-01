import json
import re
from typing import List, Dict, Any, Optional, Tuple

from src.core.llm_provider import LLMProvider
from src.telemetry.logger import logger


class ReActAgent:
    """
    A ReAct-style Agent that follows the Thought -> Action -> Observation loop.

    Expected tool format:
    {
        "name": "tool_name",
        "description": "What this tool does",
        "function": callable
    }

    Expected LLM action format:
    Action: tool_name({"arg1": "value", "arg2": 123})
    """

    def __init__(self, llm: LLMProvider, tools: List[Dict[str, Any]], max_steps: int = 5):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.history: List[Dict[str, str]] = []

    def get_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            [f"- {t['name']}: {t.get('description', 'No description')}" for t in self.tools]
        )

        return f"""
You are Travel Planner Agent, an assistant that helps users plan realistic trips.

You can use tools to collect real information before answering.
Available tools:
{tool_descriptions}

You must follow this format exactly:

Thought: explain briefly what information you need.
Action: tool_name({{"key": "value"}})

After the tool returns an observation, continue with either another tool call or the final answer.

When you have enough information, answer with:
Final Answer: your final response in Vietnamese.

Rules:
- Use tools for factual travel information such as weather, attractions, hotels/homestays, restaurants, and transport costs.
- Do not invent API results.
- Tool arguments must be valid JSON inside parentheses.
- Do not call a tool that is not listed.
- If a tool returns an error or limited data, explain that limitation honestly.
- Keep the final answer practical and structured.

Correct examples:
Action: get_weather({{"location": "Đà Nẵng", "forecast_days": 3}})
Action: search_attractions({{"location": "Đà Nẵng", "radius": 10000, "limit": 8}})
Action: search_stays({{"location": "Đà Nẵng", "radius": 5000, "limit": 5}})
Action: search_restaurants({{"location": "Đà Nẵng", "cuisine": "seafood", "limit": 5}})
Action: search_flight_cost({{"origin_code": "HAN", "destination_code": "DAD", "departure_date": "2026-06-15", "adults": 1}})
Action: build_travel_plan({{"destination": "Đà Nẵng", "days": 3, "budget_vnd": 5000000}})
""".strip()

    def run(self, user_input: str) -> str:
        logger.log_event(
            "AGENT_START",
            {
                "input": user_input,
                "model": getattr(self.llm, "model_name", "unknown"),
                "max_steps": self.max_steps,
            },
        )

        scratchpad = f"User request: {user_input}\n"
        final_answer: Optional[str] = None

        for step in range(1, self.max_steps + 1):
            logger.log_event("AGENT_STEP_START", {"step": step})

            try:
                llm_result = self.llm.generate(
                    scratchpad,
                    system_prompt=self.get_system_prompt(),
                )
            except Exception as e:
                logger.log_event("AGENT_LLM_ERROR", {"step": step, "error": str(e)})
                return f"LLM error: {str(e)}"

            content = self._extract_llm_content(llm_result)
            self.history.append({"role": "assistant", "content": content})

            logger.log_event(
                "AGENT_LLM_RESPONSE",
                {
                    "step": step,
                    "content": content,
                    "usage": llm_result.get("usage") if isinstance(llm_result, dict) else None,
                    "latency_ms": llm_result.get("latency_ms") if isinstance(llm_result, dict) else None,
                },
            )

            parsed_final = self._parse_final_answer(content)
            if parsed_final:
                final_answer = parsed_final
                logger.log_event("AGENT_FINAL_ANSWER", {"step": step})
                break

            action = self._parse_action(content)
            if not action:
                observation = (
                    "Parser error: No valid Action found. "
                    "Use format: Action: tool_name({\"key\": \"value\"}) "
                    "or provide Final Answer."
                )
                logger.log_event("AGENT_PARSE_ERROR", {"step": step, "content": content})
            else:
                tool_name, args = action
                observation = self._execute_tool(tool_name, args)
                logger.log_event(
                    "AGENT_TOOL_CALL",
                    {
                        "step": step,
                        "tool_name": tool_name,
                        "args": args,
                        "observation_preview": observation[:1000],
                    },
                )

            scratchpad += f"\n{content}\nObservation: {observation}\n"
            self.history.append({"role": "observation", "content": observation})

        if not final_answer:
            final_answer = (
                "Mình chưa thể hoàn tất câu trả lời trong số bước cho phép. "
                "Dưới đây là thông tin đã thu thập được:\n\n"
                f"{scratchpad}"
            )

        logger.log_event(
            "AGENT_END",
            {
                "steps": min(len([h for h in self.history if h["role"] == "assistant"]), self.max_steps),
                "has_final_answer": bool(final_answer),
            },
        )

        return final_answer

    def _execute_tool(self, tool_name: str, args: str) -> str:
        selected_tool = None

        for tool in self.tools:
            if tool.get("name") == tool_name:
                selected_tool = tool
                break

        if selected_tool is None:
            return f"Tool {tool_name} not found. Available tools: {self._available_tool_names()}"

        func = (
            selected_tool.get("function")
            or selected_tool.get("func")
            or selected_tool.get("callable")
        )

        if not callable(func):
            return f"Tool {tool_name} does not have a callable function."

        try:
            parsed_args = self._parse_tool_args(args)

            if isinstance(parsed_args, dict):
                result = func(**parsed_args)
            elif isinstance(parsed_args, list):
                result = func(*parsed_args)
            elif parsed_args is None:
                result = func()
            else:
                result = func(parsed_args)

            if isinstance(result, str):
                return result

            return json.dumps(result, ensure_ascii=False, indent=2)

        except json.JSONDecodeError as e:
            return (
                "Tool execution error: Action arguments must be valid JSON. "
                f"Details: {str(e)}"
            )
        except TypeError as e:
            return (
                f"Tool execution error: Invalid arguments for {tool_name}. "
                f"Details: {str(e)}"
            )
        except Exception as e:
            logger.log_event(
                "AGENT_TOOL_ERROR",
                {"tool_name": tool_name, "args": args, "error": str(e)},
            )
            return f"Tool execution error: {str(e)}"

    def _extract_llm_content(self, llm_result: Any) -> str:
        if isinstance(llm_result, dict):
            return str(llm_result.get("content", "")).strip()
        return str(llm_result).strip()

    def _parse_action(self, text: str) -> Optional[Tuple[str, str]]:
        pattern = r"Action\s*:\s*([a-zA-Z_]\w*)\s*\((.*?)\)"
        match = re.search(pattern, text, flags=re.DOTALL)

        if not match:
            return None

        tool_name = match.group(1).strip()
        args = match.group(2).strip()
        return tool_name, args

    def _parse_final_answer(self, text: str) -> Optional[str]:
        match = re.search(r"Final Answer\s*:\s*(.*)", text, flags=re.DOTALL)
        if not match:
            return None
        return match.group(1).strip()

    def _parse_tool_args(self, args: str) -> Any:
        if not args or not args.strip():
            return None
        return json.loads(args)

    def _available_tool_names(self) -> str:
        return ", ".join([tool.get("name", "unknown") for tool in self.tools])