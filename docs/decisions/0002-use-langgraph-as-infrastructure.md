# 2. Use LangGraph as Infrastructure

**Status:** Accepted

## Context

Privacy Gateway requires complex orchestration of multiple specialized agents:
- Privacy protection (detection, labeling, masking).
- Security guardrails (PromptGuard).
- Cloud LLM processing (Gemini).
- Re-identification (unmasking).

A simple linear chain is insufficient because we need:
- **Parallel execution:** Running privacy checks and security guardrails simultaneously.
- **Conditional branching:** Blocking requests if security criteria are not met.
- **State persistence:** Maintaining context across multi-turn interactions.

## Decision

We decided to use **LangGraph** as the primary orchestration engine. However, to maintain Clean Architecture principles:
1. **LangGraph lives in Infrastructure:** The graph definition (`privacy_graph.py`) is located in `src/app/infrastructure/agents/`.
2. **Nodes call Use Cases:** Instead of putting business logic inside graph nodes, nodes simply delegate work to injected Use Cases.
3. **GraphState in Domain:** The state object used by LangGraph is defined as a Pydantic model in `src/app/domain/entities.py`.

## Consequences

### Positive
- **Visualizable Flow:** The state machine can be visualized (e.g., using LangGraph Studio or Mermaid).
- **Control over Cycles:** LangGraph allows for easy implementation of retry loops and complex feedback cycles.
- **Persistence:** Built-in support for checkpointers (MemorySaver) allows for seamless multi-turn conversations.

### Negative
- **Infrastructure Dependency:** The orchestration logic is tightly coupled to the LangGraph library.
- **Asynchronous Complexity:** Requires careful handling of `async/await` throughout the graph.
