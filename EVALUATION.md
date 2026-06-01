# Evaluation Metrics for Lab 3: Agentic reasoning

In this lab, we don't just ask "Does it work?". We ask **"How well does it perform?"**.

## Key Industry Metrics

### 1. Token Efficiency (Token count)
- **Prompt vs. Completion**: Are your system prompts too verbose? Is the agent generating unnecessary "chatter" before the tool call?
- **Cost Analysis**: Lower token count = Lower cost = Higher ROI.

### 2. Latency (Response time)
- **Time-to-First-Token (TTFT)**: How quickly does the LLM start responding?
- **Total Duration**: For a ReAct agent, this includes all loops + tool execution times.
- **Goal**: In "production", users expect responses within 200ms-2s.

### 3. Loop count (Steps)
- **Multi-step Reasoning**: How many `Thought->Action` cycles did the agent need to solve the task?
- **Termination Quality**: Does the agent correctly identify when to call "Final Answer", or does it get stuck in an "endless loop"?

### 4. Failure Analysis (Error codes)
- **JSON Parser Error**: The LLM outputted `Action` in a format that your code couldn't parse.
- **Hallucination Error**: The LLM hallucinated a tool that doesn't exist.
- **Timeout**: The agent exceeded the `max_steps`.

## How to use the Logs
All these metrics are automatically captured in `logs/` directory. Use a script to parse these JSON files and calculate the **Aggregate Reliability** of your agent version 1 vs version 2.
