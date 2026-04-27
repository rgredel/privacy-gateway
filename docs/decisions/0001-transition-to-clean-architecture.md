# 1. Transition to Clean Architecture

**Status:** Accepted

## Context

The initial implementation of Privacy Gateway was built as a set of flat scripts (`privacy_gateway.py`, `app.py`, `state.py`) and a collection of agents in the `agents/` directory. While functional, this approach led to several issues:
- **Tight Coupling:** Business logic was directly dependent on specific libraries like LangChain and Microsoft Presidio.
- **Low Testability:** Testing specific logic required initializing the entire LangChain ecosystem or calling real APIs.
- **Maintenance Difficulty:** As the project grew, it became harder to track where specific business rules (e.g., how to handle PII) were implemented versus where the orchestration logic resided.

## Decision

We decided to refactor the codebase to follow **Clean Architecture** principles, as defined in `docs/antigravity_clean_architecture_llm.md`. 

Key changes include:
1. **Source Code Reorganization:** Moving all logic into `src/app/` with clear layers:
   - `domain/`: Entities (Pydantic models) and Ports (Protocols/Interfaces).
   - `use_cases/`: Orchestration of business processes.
   - `infrastructure/`: Implementations of ports using specific libraries (LangChain, Presidio, etc.).
   - `interfaces/`: Application entry points (API, CLI, UI).
2. **Dependency Inversion:** Use cases now depend on Protocols (interfaces) rather than concrete implementations.
3. **Pydantic V2:** Standardization of all data structures using Pydantic for validation and structured output.

## Consequences

### Positive
- **Improved Testability:** Use cases can now be unit-tested using standard mocks without any LangChain dependencies.
- **Library Agnostic Domain:** We can swap LangChain for another library or upgrade Presidio without touching the core business logic.
- **Clearer Structure:** Developers know exactly where to find domain rules versus infrastructure details.

### Negative / Challenges
- **Initial Migration Effort:** Requires significant effort to move and rewrite existing logic from the flat structure.
- **Increased Boilerplate:** More files and folders (Protocols, Factories, Dependency Injection).
- **Learning Curve:** Developers must understand Clean Architecture patterns to contribute effectively.
