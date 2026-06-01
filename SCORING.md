# Lab Scoring Rubric: Chatbot vs ReAct Agent

This document outlines the grading criteria for Lab 3. The goal is to demonstrate deep understanding of agentic reasoning, robust monitoring, and iterative improvement.

## 👥 1. Group Score (45 Points Base + 15 Points Bonus = Max 60)

This score reflects the collective output of the team. The total group score (Base + Bonus) is capped at **60 points**.

| Category | Description | Points |
| :--- | :--- | :--- |
| **Chatbot Baseline** | Implementation of a clean, minimal chatbot baseline. | 2 |
| **Agent v1 (Working)** | Successful implementation of the ReAct loop (2+ tools). | 7 |
| **Agent v2 (Improved)** | Improved agent logic addressing failures identified in v1. | 7 |
| **Tool Design Evolution** | Clear documentation of tool spec progression. | 4 |
| **Trace Quality** | Documentation of both successful and failed traces. | 9 |
| **Evaluation & Analysis** | Data-driven comparison (Chatbot vs Agent). | 7 |
| **Flowchart & Insight** | Visual logic diagram and group learning points. | 5 |
| **Code Quality** | Clean code, modularity, and telemetry integration. | 4 |

> [!TIP]
> **Group Submission**: Teams must use the [TEMPLATE_GROUP_REPORT.md] ìn the `report/group_report/` for their final submission.

### 🎁 Group Bonus Points (Max +15)

Bonus points can be earned to reach the **60-point cap** or to compensate for missed base points:

| Bonus Category | Description | Points |
| :--- | :--- | :--- |
| **Extra Monitoring** | Adding complex industry metrics (Cost, Token ratio, etc.). | +3 |
| **Extra Tools** | Implementing advanced tools (Browsing, Search, etc.). | +2 |
| **Failure Handling** | Sophisticated retry logic or guardrails. | +3 |
| **Live System Demo** | Successful live demonstration to the instructor. | +5 |
| **Ablation Experiments** | Comparison of prompt/tool variations. | +2 |

---

## 👤 2. Individual Score (40 Points)

To earn the full 40 points, each student must submit an `individual_report.md` in the `report/individual_reports/` directory.

| Component | Rubric / Requirement | Points |
| :--- | :--- | :--- |
| **I. Technical Contribution** | List of specific code modules, tools, or tests implemented. Evidence of code quality and clarity. | 15 |
| **II. Debugging Case Study** | A detailed analysis of at least one failure (hallucination, loop, parser error) and how it was resolved using Telemetry/Logs. | 10 |
| **III. Personal Insights** | A deep reflection on the fundamental differences between LLM Chatbots vs ReAct Agents based on the lab results. | 10 |
| **IV. Future Improvements** | Proprosal for scaling this agent to a production-level RAG or multi-agent system. | 5 |

---

## 🏎️ Total Score Calculation

The final grade for each student is calculated as:
**Total = MIN(60, Group Base + Group Bonus) + Individual Score (max 40) = 100 Points Max**

> [!IMPORTANT]
> **Scoring Transparency**: The detailed template for the individual report can be found at `report/individual_reports/TEMPLATE_INDIVIDUAL_REPORT.md`.

> [!IMPORTANT]
> **Accountability**: The 40% individual weighting is designed to ensure every student contributes significantly and understands the underlying mechanics of the agentic loop.

---

> [!IMPORTANT]
> **"Fail Early, Learn Fast"**: We value the quality of your **Error Analysis** as much as the final working code. A well-documented failure trace is worth more than a "perfect" system with no explanation.
