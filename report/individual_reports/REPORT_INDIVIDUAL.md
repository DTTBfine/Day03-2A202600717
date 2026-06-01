# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Đỗ Thị Thanh Bình
- **Student ID**: 2A202600717
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

My main contribution in this lab was building the core Travel Planner Agent from the initial skeleton into a complete working system. I implemented the full agent loop, designed the initial set of travel-related tools, created the testing workflow, built the user interface, and added multi-turn conversation support so that the system could behave more like a real travel assistant instead of a one-turn chatbot.

- **Main Components Implemented**:
  - Full ReAct-style agent loop
  - Initial travel agent tools
  - Testing workflow for checking agent behavior
  - Chatbot user interface
  - Multi-turn conversation handling
  - Conversation history support
  - Integration between agent reasoning, tool execution, and final response generation

- **Code Highlights**:

### 1. Full ReAct-Style Agent Loop

I completed the main agent loop so the system can follow the structure:

```text
Thought → Action → Observation → Thought → ... → Final Answer
```

In this workflow, the model does not immediately generate the final answer. Instead, it first reasons about the user request, decides which action should be taken, executes the selected tool, receives an observation, and then continues reasoning based on that observation.

This implementation is the most important part of the project because it changes the system from a direct-response chatbot into a tool-using agent. A normal chatbot may answer fluently but can easily hallucinate travel information. The agentic version can collect supporting information before generating the final travel plan.

### 2. Initial Travel Agent Tools

I designed and implemented the first version of the travel-related tools used by the agent. These tools allow the system to gather useful travel information from external sources or heuristic calculations before producing the final response.

The initial tool set includes:

- Location search and location normalization
- Weather information lookup
- Hotel or homestay search
- Restaurant and food-place search
- Tourist attraction search
- Transportation cost estimation
- Travel plan synthesis

These tools make the system more grounded because the agent can use observations from the environment rather than relying only on the language model's internal knowledge.

### 3. Testing Workflow

I also created a testing workflow to evaluate the agent before connecting it to the final interface. This helped verify whether the agent could correctly understand user travel requests, select suitable tools, process observations, and produce a useful final answer.

The testing workflow was used to check several important cases:

- A complete request with destination, origin, budget, and trip duration
- A vague request such as wanting to go to the beach or mountains
- A request missing the starting location
- A request focused on restaurants or local food
- A request requiring transportation cost estimation
- A multi-step travel planning request

This made debugging easier because each part of the workflow could be tested separately before running the full application.

### 4. User Interface Design

I designed the chatbot interface so users could interact with the system in a simple and familiar way. Instead of requiring users to run commands manually, the system provides a chat-style interface where users can enter travel requests and receive structured plans.

The interface supports:

- Sending natural language travel requests
- Displaying the assistant's responses clearly
- Testing the agent repeatedly during development
- Making the project easier to demonstrate
- Creating a more realistic user experience

This contribution helped turn the project from a backend prototype into a usable travel planning assistant.

### 5. Multi-Turn Conversation Support

I added multi-turn support so the chatbot can understand follow-up messages in the same conversation. This is important because travel planning is usually not completed in one message. Users often provide details gradually.

For example, a user may first say:

```text
I want to go to the beach for 3 days.
```

Then continue with:

```text
My budget is 5 million VND.
```

With multi-turn support, the system can combine the new information with the previous context instead of treating the second message as an unrelated request. This makes the chatbot more natural and closer to a real travel assistant.

- **Documentation**:

My implementation connects directly with the ReAct concept from the lab. The agent first identifies what information is needed, chooses a suitable action, receives an observation from the environment, and then uses that observation to continue reasoning. This makes the answer more reliable than a baseline chatbot because the final plan is based on collected information such as weather, attractions, restaurants, accommodation options, and transportation estimates.

---

## II. Debugging Case Study (10 Points)

- **Problem Description**:

One major issue I encountered was that the agent sometimes produced unstable or incomplete intermediate outputs during the reasoning process. For example, when the user gave a broad request such as wanting to go to the beach with a certain budget, the model sometimes returned extra explanation around the structured output or missed some fields that were needed by the next step.

This caused the following problems:

- The agent could not always extract all required travel information correctly.
- Some tool calls received incomplete arguments.
- The final answer sometimes lacked important details such as starting location, budget assumptions, or transportation notes.
- The workflow became less reliable when the user request was vague.

- **Log Source**:

During testing, the logs showed cases where the extracted travel information was incomplete or included assumptions. A simplified example is:

```json
{
  "event": "VALIDATION_RESULT",
  "data": {
    "is_valid": true,
    "missing_fields": [],
    "assumptions": ["User did not provide origin point, using default."],
    "user_message": "I want to go to the beach this summer, budget 10 million VND for 2 people, 3 days 2 nights"
  }
}
```

This showed that the agent was trying to continue even when some user information was not explicit enough.

- **Diagnosis**:

The root cause was a combination of prompt design and input validation. The model could understand the user's general intention, but it sometimes tried to fill missing information by making assumptions. This is risky in a travel planning system because missing information such as the starting location affects transportation cost, route suggestions, and total budget.

Another issue was that natural language travel requests are often incomplete. Users may mention the destination but not the origin, or mention the budget but not the number of people. Without validation, the agent may continue with incorrect assumptions.

- **Solution**:

I improved the workflow by adding stronger validation and clearer rules for missing information. Instead of allowing the agent to freely assume important fields, the system checks whether essential travel information is available. If a required field is missing, the agent either asks for clarification or clearly states the limitation in the final answer.

I also improved the parsing and fallback logic so the system could better handle Vietnamese travel expressions such as:

- “10 triệu”
- “2 người”
- “3 ngày 2 đêm”
- “đi biển”
- “nghỉ dưỡng”

After this fix, the agent became more stable. It was better at extracting useful information, avoiding unsupported assumptions, and producing more reliable travel plans.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

### 1. Reasoning: How did the `Thought` block help the agent compared to a direct Chatbot answer?

The `Thought` step helped the agent break down the user's request before answering. A direct chatbot usually generates a response immediately, so it may sound natural but may not check whether the information is complete or grounded.

With the ReAct-style approach, the agent can first reason about what the user wants, what information is missing, and which tool should be used next. This is especially useful for travel planning because a good answer often depends on many factors: destination, starting location, number of days, budget, weather, food preferences, attractions, and transportation.

For example, if the user asks for a 3-day beach trip, the agent should not immediately invent a plan. It should first identify whether the destination is specific or vague, whether the starting point is available, and whether external information is needed. This makes the final answer more structured and reliable.

### 2. Reliability: In which cases did the Agent actually perform worse than the Chatbot?

The agent performed worse than a simple chatbot in some cases:

| Scenario | Why the Chatbot Was Better | Why the Agent Was Worse |
| :--- | :--- | :--- |
| Simple general questions | The chatbot can answer immediately | The agent may add unnecessary reasoning and tool calls |
| Creative writing requests | The chatbot is faster and more direct | The agent workflow is not needed |
| External tool failure | The chatbot can still provide a general answer | The agent may return incomplete observations |
| Rate limit or timeout | The chatbot may need only one model call | The agent may need multiple calls and become slower |
| Very short user prompts | The chatbot can infer a quick answer | The agent may need clarification or validation |

This showed me that agents are not always better than chatbots. Agents are better when the task requires reasoning, tools, or external information. For simple conversation, a direct chatbot can be faster and more efficient.

### 3. Observation: How did the environment feedback influence the next steps?

The observation step is what makes the agent different from a normal chatbot. After the agent takes an action, it receives information from a tool or validation step. That information changes what the agent does next.

For example:

```text
Thought: The user wants a beach trip, but the destination is not specific.
Action: Recommend possible beach destinations.
Observation: The system suggests Da Nang, Nha Trang, and Phu Quoc.

Thought: I should compare these destinations using weather, attractions, restaurants, stays, and transportation cost.
Action: Collect travel information for the selected destinations.
Observation: Weather, places, food options, accommodation suggestions, and cost estimates are returned.

Thought: Now I can generate a plan based on the observations instead of guessing.
Final Answer: A structured travel plan with recommendations and limitations.
```

The key insight is that observations reduce hallucination. The agent can adjust its final response based on tool results, missing fields, or errors. If the tool does not provide exact hotel prices, the agent should not invent them. If the origin is missing, the agent should not pretend to know transportation cost.

---

## IV. Future Improvements (5 Points)

- **Scalability**:

The system can be improved by running independent tool calls in parallel. Weather lookup, restaurant search, attraction search, and accommodation search do not always depend on each other, so they can be executed asynchronously to reduce latency.

For larger systems, a more formal workflow graph could be used to manage branching logic, retries, and multi-step planning. This would make the agent easier to scale when more tools are added.

- **Safety**:

A supervisor layer could be added to check the agent's actions before execution. This layer could validate tool arguments, detect unsafe or unsupported requests, and prevent the final answer from making false claims.

The system should also avoid exposing private user information, raw errors, or internal configuration details. Conversation history should be treated as user data and handled carefully.

- **Performance**:

Caching should be added for repeated location, weather, and place-search results. This would reduce external API calls and improve response speed.

The system could also use better ranking for destination recommendations. Instead of only returning possible places, it could score each destination based on budget fit, travel time, weather, attractions, and user preferences.

- **Future Features**:

Possible future improvements include:

- Real flight, train, bus, and hotel price integration
- Map-based display of attractions and restaurants
- Better personalization based on previous user preferences
- More robust handling of Vietnamese travel expressions
- Streaming responses to improve user experience
- A monitoring dashboard for latency, tool success rate, and failure types

Overall, I learned that building an agent is not only about calling tools. A reliable agent also needs validation, fallback handling, good prompts, clear observations, and a user interface that supports realistic multi-turn interaction.
