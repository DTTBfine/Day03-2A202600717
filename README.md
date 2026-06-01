# Lab 3: Chatbot vs ReAct Agent (Industry Edition)

Welcome to Phase 3 of the Agentic AI course! This lab focuses on moving from a simple LLM Chatbot to a sophisticated **ReAct Agent** with industry-standard monitoring.

## 🚀 Getting Started

### 1. Setup Environment
Copy the `.env.example` to `.env` and fill in your API keys:
```bash
cp .env.example .env
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Directory Structure
- `src/tools/`: Extension point for your custom tools.

## 🏠 Running with Local Models (CPU)

If you don't want to use OpenAI or Gemini, you can run open-source models (like Phi-3) directly on your CPU using `llama-cpp-python`.

### 1. Download the Model
Download the **Phi-3-mini-4k-instruct-q4.gguf** (approx 2.2GB) from Hugging Face:
- [Phi-3-mini-4k-instruct-GGUF](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf)
- Direct Download: [phi-3-mini-4k-instruct-q4.gguf](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf)

### 2. Place Model in Project
Create a `models/` folder in the root and move the downloaded `.gguf` file there.

### 3. Update `.env`
Change your `DEFAULT_PROVIDER` and set the path:
```env
DEFAULT_PROVIDER=local
LOCAL_MODEL_PATH=./models/Phi-3-mini-4k-instruct-q4.gguf
```

## 🎯 Lab Objectives

1.  **Baseline Chatbot**: Observe the limitations of a standard LLM when faced with multi-step reasoning.
2.  **ReAct Loop**: Implement the `Thought-Action-Observation` cycle in `src/agent/agent.py`.
3.  **Provider Switching**: Swap between OpenAI and Gemini seamlessly using the `LLMProvider` interface.
4.  **Failure Analysis**: Use the structured logs in `logs/` to identify why the agent fails (hallucinations, parsing errors).
5.  **Grading & Bonus**: Follow the [SCORING.md](file:///Users/tindt/personal/ai-thuc-chien/day03-lab-agent/SCORING.md) to maximize your points and explore bonus metrics.

## 🛠️ How to Use This Baseline

The code is designed as a **Production Prototype**. It includes:
- **Telemetry**: Every action is logged in JSON format for later analysis.
- **Robust Provider Pattern**: Easily extendable to any LLM API.
- **Clean Skeletons**: Focus on the logic that matters—the agent's reasoning process.

## 📋 Input Validation Tool

The `validate_travel_input` tool validates and normalizes user requests before calling travel APIs.

### Features:
- Extracts: origin, destination, budget, people, days, nights, season, interests
- Supports Vietnamese text parsing:
  - "10 triệu" → budget=10000000
  - "2 người" → people=2
  - "3 ngày 2 đêm" → days=3, nights=2
- Handles missing information with assumptions and follow-up questions

### Usage:
```python
from src.tools.travel_api_tools import validate_travel_input

result = validate_travel_input("T muốn đi biển budget 10 triệu cho 2 người, đi 3 ngày 2 đêm")
# Returns:
# {
#   "is_valid": true,
#   "missing_fields": [],
#   "normalized_input": {...},
#   "assumptions": [],
#   "follow_up_question": null
# }
```

## ⚡ Async Research Pipeline

Research tools run **asynchronously** for faster performance:

- Multiple destinations are researched **in parallel**
- Within each destination, independent API calls run **concurrently**:
  - geocode → weather
  - geocode → attractions
  - geocode → stays
  - geocode → restaurants
  - (if origin provided) → transport cost

### Timeouts:
| Tool | Timeout |
|------|---------|
| Geocode | 10s |
| Weather | 10s |
| Overpass (attractions/stays/restaurants) | 20s |
| Total research per destination | 30s |

### Error Handling:
- If one API fails, others continue
- Partial results are returned with error flags
- No crashes from individual tool failures

## 🔌 Public APIs Used

| API | Provider | Purpose |
|-----|----------|---------|
| Nominatim | OpenStreetMap | Geocoding (location → coordinates) |
| Open-Meteo | open-meteo.com | Weather forecast |
| Overpass API | OpenStreetMap | POI search (attractions, hotels, restaurants) |
| Haversine | Local | Transport cost estimation |

No API keys required for these services.

## 🚀 Running the Project

### CLI Single-Shot
```bash
python test.py "T muốn đi du lịch gần biển mùa hè này, budget 10 triệu cho 2 người, đi 3 ngày 2 đêm"
```

### CLI Chatbot
```bash
python chatbot.py
# Then type: Tôi muốn đi biển budget 10 triệu
# Bot: Bạn đi mấy người, mấy ngày và xuất phát từ đâu?
# Type: 2 người, 3 ngày, từ TP.HCM
# Bot: generates plan
```

### Streamlit Web UI
```bash
streamlit run app.py
```

## 📊 Expected Behavior

### Input Validation
- **Valid input**: Continues to research and generate plan
- **Invalid input**: Asks follow-up questions
- **Missing info with defaults**: Proceeds with assumptions logged

### Async Research
- Research for multiple destinations runs in parallel
- Response time significantly faster than sequential execution
- Logs show individual tool latencies and success/failure

---

*Happy Coding! Let's build agents that actually work.*
