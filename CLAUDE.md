# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Streamlit web UI
streamlit run app.py

# Run the CLI chatbot (multi-turn, persists history to history.json)
python chatbot.py

# Run the single-shot travel planner (accepts query as args or stdin)
python test.py "Lập plan 3 ngày đi Đà Nẵng từ Hà Nội, ngân sách 5 triệu"

# Run a specific test
python tests/test_local.py
pytest tests/
```

## Environment Setup

Copy `.env.example` to `.env`. Required variables:

| Variable | Purpose |
|---|---|
| `DEFAULT_PROVIDER` | `openai` / `google` / `gemini` / `local` |
| `DEFAULT_MODEL` | Model name (optional, has defaults) |
| `OPENAI_API_KEY` | Required when provider is `openai` |
| `GEMINI_API_KEY` | Required when provider is `google`/`gemini` |
| `LOCAL_MODEL_PATH` | Path to `.gguf` file when provider is `local` |
| `MAX_DESTINATION_OPTIONS` | Max destinations to research (default: 3) |

## Architecture

This is a Vietnamese travel planning system with two execution modes sharing the same agent pipeline.

### Execution Modes

- **`app.py`** — Streamlit web UI; wraps `chatbot.py` functions with a chat interface
- **`chatbot.py`** — Multi-turn CLI; persists conversation to `history.json`; calls into the pipeline defined in `test.py`
- **`test.py`** — Single-shot CLI; also defines the entire agent pipeline (all agents live here despite the filename)

### Multi-Agent Pipeline (all in `test.py`)

Each user request flows through four sequential agents:

1. **`intent_agent`** — LLM call that extracts structured trip params (destination, origin, days, budget, theme, etc.) from natural language. Falls back to regex (`_fallback_extract`) on JSON parse failure.
2. **`destination_agent`** — Resolves vague requests ("đi biển") to concrete destination candidates. Skips LLM call if destination was already specific; falls back to hardcoded lists by theme.
3. **`research_agent`** (called via `collect_research_for_destinations`) — Pure tool call, no LLM. Calls `get_weather`, `search_attractions`, `search_stays`, `search_restaurants`, and optionally `estimate_transport_cost` for each candidate destination.
4. **`planning_agent`** — LLM call that synthesizes all research into a structured itinerary comparing all destination options.

For multi-turn conversations, `chatbot.py`'s `rewrite_user_request` runs a preliminary LLM call to merge the new message with recent history into a standalone request before the pipeline runs.

### LLM Provider System (`src/core/`)

`LLMProvider` (abstract base) defines `generate()` and `stream()`. Concrete implementations: `OpenAIProvider`, `GeminiProvider`, `LocalProvider`. All return `{"content": str, "usage": dict, "latency_ms": int}`. Provider selection is done in `create_llm_provider()` in `test.py` via `DEFAULT_PROVIDER` env var.

### Travel Tools (`src/tools/travel_api_tools.py`)

All tools use free public APIs — no API keys required:
- **Geocoding**: Nominatim (OpenStreetMap)
- **Weather**: Open-Meteo
- **POI search** (attractions, stays, restaurants): Overpass API
- **Transport cost**: Local heuristic calculation using haversine distance

`TRAVEL_TOOLS` list at the bottom of the file is the registry used by `ReActAgent`.

### ReAct Agent (`src/agent/agent.py`)

`ReActAgent` implements the Thought→Action→Observation loop. The LLM must respond with `Action: tool_name({"key": "value"})` or `Final Answer: ...`. The agent parses actions with regex, executes the matching tool from its `tools` list, appends observations to the scratchpad, and repeats up to `max_steps`. Logs every step via `src/telemetry/logger.py`.

### Telemetry

`IndustryLogger` (singleton `logger`) writes JSON-structured events to `logs/YYYY-MM-DD.log`. Events: `AGENT_START`, `AGENT_STEP_START`, `AGENT_LLM_RESPONSE`, `AGENT_TOOL_CALL`, `AGENT_PARSE_ERROR`, `AGENT_FINAL_ANSWER`, `AGENT_END`.

### Conversation History

Stored as a JSON array in `history.json` (root dir). Each entry: `{timestamp, role, content, metadata?}`. `chatbot.py` trims to the last 8 messages (`MAX_HISTORY_MESSAGES`) when passing context to the LLM.

## Key Design Constraints

- All LLM prompts instruct the model to return only raw JSON (no markdown, no explanation). JSON parsing uses `_parse_json_object` / `_parse_json_array` with regex stripping of code fences.
- Tools return Vietnamese-language error messages; the planning agent is instructed not to hallucinate data when tools fail.
- `transport` is `None` when `origin` is missing — the planning agent must not invent transport costs in that case.
- The `ReActAgent` in `src/agent/agent.py` is the lab skeleton for students to implement/improve; the production pipeline in `test.py` does not use it directly.
