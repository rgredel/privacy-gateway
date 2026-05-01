# ADR-0008: Dynamic Model Orchestration Factory

## Status
Accepted

## Context
As the project evolved to support both local (Ollama) and cloud (Gemini) models, hardcoding model initialization within services led to tight coupling and poor scalability. Users needed the ability to switch models dynamically per request (e.g., choosing Bielik for local NER and Gemini for final response generation) via the LangGraph state.

## Decision
We implemented a **Dynamic Model Factory** (`src/app/infrastructure/llm/factory.py`) that acts as a central router for LLM instances.

Key features:
1. **Dynamic Routing**: The `get_model(model_name)` function automatically instantiates the correct provider (ChatOllama vs ChatGoogleGenerativeAI) based on the string identifier.
2. **State-Driven Selection**: Use cases and graph nodes pass the `model_name` from the `GraphState` directly to the factory.
3. **Decoupling**: Services no longer care about *how* a model is created or which provider it uses; they only interact with the standard LangChain interface.

## Consequences
- **Positive**: High flexibility in orchestrating multi-model pipelines. Easier to benchmark different models by just changing a parameter in the UI.
- **Negative**: Slight overhead of dynamic instantiation (negligible compared to LLM latency).
- **Maintenance**: Adding a new provider (e.g., Anthropic) now only requires an update to the factory, not the whole application.
