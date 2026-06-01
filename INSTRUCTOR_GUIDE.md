# Instructor Guide: Lab 3 - From Chatbot to Agentic ReAct

This guide is designed for instructors to lead a 240-minute (4-hour) intensive laboratory session. The goal is to move students from "writing code that runs" to "engineering systems that reason and evolve."

---

## 🎯 Core Learning Objectives
1.  **ReAct Mechanics**: Understand the cycle of *Thought -> Action -> Observation*.
2.  **Industry Observability**: Learn to debug an LLM "brain" using structured JSON logs.
3.  **Iterative Refinement**: Improve performance by diagnosing failure traces, not just guessing prompts.

---

## ⏱️ Timeline & Flow

### 01. The Hook: Why Agents? (15m)
- **Demo**: Show a simple chatbot failing a multi-step query (e.g., "Find the cheapest price and calculate total cost with 10% tax").
- **Key Insight**: Chatbots are good at talking; Agents are good at *acting*.

### 02. Phase 1: Tool Design (30m)
- **Activity**: Students define tools in `src/tools/`.
- **Teaching Point**: Stress the importance of **Tool Descriptions**. An LLM only knows a tool through its string description.
- **Example**: Compare a vague description ("Calculates tax") vs a precise one ("Calculates 10% VAT for EU countries only, takes float amount").

### 03. Phase 2: Chatbot Baseline (30m)
- **Activity**: Run `chatbot.py` against complex test cases.
- **Observe**: Many students will try to "prompt engineer" the chatbot to solve multi-step problems. Let them fail. This sets the stage for ReAct.

### 04. Phase 3: Building Agent v1 (60m) - The Core Lab
- **Activity**: Implementing `agent/agent.py`.
- **Instructor's Role**: Help with Regex/JSON parsing (the most common bottleneck). Ensure they understand that the `Observation` must be fed back into the prompt for the next step.

### 05. Phase 4: Failure Analysis (45m) - CRITICAL
- **Activity**: Open the `logs/` directory. Look for `LOG_EVENT: LLM_METRIC`.
- **Teaching Case**: Find a case where the agent chose the wrong tool or hallucinated arguments.
- **Fix**: Guide students to update their system prompt (v1 -> v2) or tool specs based on these *facts*, not intuition.

### 06. Phase 5: Group Evaluation (30m)
- **Activity**: Run the full test suite. Generate the tables for `GROUP_REPORT`.
- **Discussion**: Why did the Agent win in multi-step scenarios? Why did the Chatbot win in simple Q&A?

---

## 💡 Teaching Tips & Examples

### 🏦 Recommended Scenario: "The Smart E-commerce Assistant"
- **Tool 1**: `check_stock(item_name)` -> Returns available quantity.
- **Tool 2**: `get_discount(coupon_code)` -> Returns percentage.
- **Tool 3**: `calc_shipping(weight, destination)` -> Returns cost.
- **Test Case**: "I want to buy 2 iPhones using code 'WINNER' and ship to Hanoi. What is the total price?"

### ⚠️ Common Pitfalls to Watch For
1.  **Infinite Loops**: The agent repeats the same "Thought" forever.
    - *Fix*: Check the `max_steps` implementation and the "Final Answer" detection.
2.  **JSON Errors**: The LLM outputs markdown backticks (e.g., ```json ... ```) which the parser might skip.
    - *Fix*: Teach students to use robust extraction or instruct the LLM specifically to "Only output raw JSON."
3.  **Empty Observations**: A tool returns "No data found".
    - *Fix*: How does the agent react to failure? Does it try another tool or give up?

---

## 📈 Success Metrics for the Instructor
Your lab is successful if:
- Students can show you a **Failed Trace** and explain *why* it failed.
- Students can demonstrate **Provider Switching** (OpenAI -> Gemini) and compare latency.
- Every student has an **Individual Report** that reflects personal technical contributions.

---

*“In the world of AI, the trace is the truth. Teach them to read the logs.”*
