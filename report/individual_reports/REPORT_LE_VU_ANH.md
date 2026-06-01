# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Lê Vũ Anh
- **Student ID**: 2A202600809
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

*Describe your specific contribution to the codebase (e.g., implemented a specific tool, fixed the parser, etc.).*

- **Modules Implemented**: `src/tools/travel_api_tools.py`, `src/agent/agent.py`, `src/telemetry/logger.py`

- **Code Highlights**:

### 1. ReAct Agent Loop (`src/agent/agent.py`)

```python:69:152:src/agent/agent.py
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
            # Thought -> Action -> Observation cycle
            llm_result = self.llm.generate(scratchpad, system_prompt=self.get_system_prompt())
            content = self._extract_llm_content(llm_result)
            
            # Check for Final Answer
            parsed_final = self._parse_final_answer(content)
            if parsed_final:
                final_answer = parsed_final
                break
            
            # Execute tool
            action = self._parse_action(content)
            if action:
                tool_name, args = action
                observation = self._execute_tool(tool_name, args)
                scratchpad += f"\n{content}\nObservation: {observation}\n"
```

### 2. Async Research Pipeline (`src/tools/travel_api_tools.py`)

```python:984:1045:src/tools/travel_api_tools.py
async def research_all_destinations_async(
    destinations: list,
    params: dict,
) -> list:
    """
    Research all destinations in parallel.
    """
    tasks = [
        research_destination_async(
            option.get("destination", option),
            params,
            option,
        )
        for option in destination_options
    ]
    
    # Run all in parallel with overall timeout
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=TIMEOUT_TOTAL_RESEARCH,
    )
```

### 3. Input Validation Tool

```python:602:800:src/tools/travel_api_tools.py
def validate_travel_input(user_message: str) -> Dict[str, Any]:
    """
    Validate and normalize user's travel request.
    Extracts: origin, destination, budget, people, days, nights, season, and interests.
    """
    # Supports Vietnamese text parsing:
    # "10 triệu" → budget=10000000
    # "2 người" → people=2
    # "3 ngày 2 đêm" → days=3, nights=2
```

- **Documentation**: 
  - **ReAct Loop**: The agent follows `Thought → Action → Observation` cycle. The LLM generates `Thought` and `Action`, the system executes the tool and returns `Observation`, then loops until `Final Answer`.
  - **Async Pipeline**: Multiple destinations are researched in parallel; within each destination, independent API calls (geocode → weather, attractions, stays, restaurants) run concurrently.
  - **Error Handling**: Each tool has timeout (10s for geocode/weather, 20s for Overpass) and graceful fallback with error flags.

---

## II. Debugging Case Study (10 Points)

*Analyze a specific failure event you encountered during the lab using the logging system.*

- **Problem Description**: Agent encountered **OpenAI API Rate Limit (429 Too Many Requests)**

```
Error code: 429 - {'error': {'code': '429', 'message': 'Too many requests', 'type': 'limitation'}}
```

- **Log Source**: From `logs/2026-06-01.log`:

```json
{"timestamp": "2026-06-01T10:34:07.606126", "event": "VALIDATION_RESULT", "data": {"is_valid": true, "missing_fields": [], "assumptions": ["User did not provide origin point, using default."], "user_message": "T muốn đi biển mùa hè này, budget 10 triệu cho 2 người, đi 3 ngày 2 đêm"}}
```

- **Diagnosis**:
  1. **Root Cause**: OpenAI API rate limit exceeded when running multiple test requests in succession
  2. **Why it happened**: Sequential calls to `intent_agent`, `destination_agent`, and `planning_agent` all use the same LLM endpoint
  3. **Model behavior**: GPT-4o has rate limits based on tokens/minute and requests/minute tier

- **Solution**:
  1. Added delay between test runs (5 seconds)
  2. Used more specific destination request to reduce LLM calls
  3. Alternative: Implement request queuing with exponential backoff
  4. Alternative: Use caching for repeated location queries

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

*Reflect on the reasoning capability difference.*

### 1. Reasoning: How did the `Thought` block help the agent compared to a direct Chatbot answer?

**Chatbot**: Direct response based on pattern matching - no explicit reasoning chain
**ReAct Agent**: Explicit `Thought` step forces the model to articulate:
- What information is needed?
- Why is this information relevant?
- What tool should be called next?

```
# Chatbot response (hypothetical):
"Đi biển 10 triệu cho 2 người? Bạn có thể đi Nha Trang..."

# ReAct Agent reasoning:
Thought: User wants beach vacation with 10M VND for 2 people. 
         I need to check weather, attractions, and transport costs.
Action: get_weather({"location": "Nha Trang", "forecast_days": 3})
Observation: Rain probability 81-100% for next 3 days
```

The `Thought` block prevents **hallucination** - the agent cannot invent API results because it must wait for real `Observation` before proceeding.

### 2. Reliability: In which cases did the Agent actually perform *worse* than the Chatbot?

| Scenario | Chatbot Advantage | ReAct Agent Limitation |
|----------|------------------|----------------------|
| **Simple factual questions** | Instant answer | Unnecessary overhead |
| **No tool needed** | Direct response | Forced to use tools anyway |
| **Rate limiting** | May still work | Fails completely |
| **LLM cost** | 1 API call | 3-5+ API calls per query |
| **Latency** | Fast | 10-30s for full research |

### 3. Observation: How did the environment feedback (observations) influence the next steps?

The `Observation` step creates a **feedback loop**:

```
Step 1: Thought → Action: get_weather(Nha Trang)
         Observation: Rain probability 100% on Day 1

Step 2: Thought → Action: search_attractions(Nha Trang)
         Observation: Found 5 attractions including indoor options

Step 3: Thought → Final Answer with weather caveat
```

**Key insight**: Without `Observation`, the agent would suggest outdoor activities blindly. With real-time feedback, it can:
1. Warn about bad weather
2. Suggest indoor alternatives
3. Adjust budget calculations based on actual transport data

---

## IV. Future Improvements (5 Points)

*How would you scale this for a production-level AI agent system?*

### Scalability

- **Async Message Queue**: Replace sequential tool calls with a proper message queue (RabbitMQ, Redis Queue)
- **Horizontal Scaling**: Deploy agent workers behind a load balancer to handle multiple concurrent requests
- **Tool Registry**: Implement dynamic tool discovery for systems with 100+ tools

### Safety

- **Supervisor LLM**: Add a "guardian" agent that audits tool calls before execution
  - Check for potentially harmful actions (deleting data, spending money)
  - Validate tool arguments against schema
- **Rate Limiting**: Per-user/request quotas to prevent abuse
- **Audit Logging**: Immutable log storage for compliance

### Performance

- **Vector DB for Tool Retrieval**: When tools grow to 50+, use embeddings to retrieve relevant tools based on user intent
- **Response Caching**: Cache common location/weather queries to reduce API calls
- **Streaming Responses**: Implement streaming to reduce perceived latency

```python
# Example: Supervisor pattern
class SupervisorAgent:
    def review_action(self, action: ToolCall) -> bool:
        """Pre-execution safety check"""
        if action.tool_name == "send_money":
            return False  # Block financial transactions
        if action.tool_name == "delete_user":
            return False  # Require human approval
        return True
```

---

> [!NOTE]
> Submit this report by renaming it to `REPORT_[YOUR_NAME].md` and placing it in this folder.
