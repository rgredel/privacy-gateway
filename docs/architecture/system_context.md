# System Context & Containers

This document describes the high-level architecture of the Privacy Gateway and its integration with external systems.

## High-Level System Context (C4)

Privacy Gateway acts as a secure intermediary between users and potentially unsafe/non-private Large Language Models.

```mermaid
C4Context
    title System Context Diagram - Privacy Gateway

    Person(user, "User", "Sends queries containing PII or sensitive context.")
    
    System(gateway, "Privacy Gateway", "Processes queries, masks PII, and validates security.")
    
    System_Ext(ollama, "Local LLM (Ollama)", "Provides local inference for PII detection (Llama 3/Bielik).")
    System_Ext(gemini, "Cloud LLM (Gemini 2.5)", "Provides high-performance processing for masked data.")
    System_Ext(presidio, "Microsoft Presidio", "Local NER engine for fast PII detection.")

    Rel(user, gateway, "Sends query & data", "HTTPS/Websocket")
    Rel(gateway, presidio, "Detects basic PII", "In-process call")
    Rel(gateway, ollama, "Refines PII detection", "HTTP / Local API")
    Rel(gateway, gemini, "Processes masked query", "HTTPS / Cloud API")
    
    UpdateRelStyle(user, gateway, $textColor="blue", $lineColor="blue")
```

## Internal Containers (Clean Architecture)

The system is organized into layers to ensure separation of concerns and maintainability.

```mermaid
C4Container
    title Container Diagram - Privacy Gateway Internal

    Container_Boundary(src_app, "Source Code (src/app)") {
        Container(interfaces, "Interfaces (UI/API)", "Chainlit / FastAPI", "Handles user interaction and session management.")
        Container(use_cases, "Use Cases", "Python Logic", "Orchestrates business rules (Detection, Masking, etc.).")
        Container(domain, "Domain Layer", "Pydantic Entities", "Defines business objects and protocols (ports).")
        Container(infrastructure, "Infrastructure Layer", "LangGraph / Adapters", "Implements external API calls and graph orchestration.")
    }

    Rel(interfaces, use_cases, "Invokes")
    Rel(use_cases, domain, "Uses entities")
    Rel(infrastructure, domain, "Implements ports")
    Rel(use_cases, infrastructure, "Calls via ports", "Dependency Inversion")
```

### Key Components

1. **Interfaces**: Currently implemented using **Chainlit** for the web UI and a CLI for testing.
2. **Use Cases**: Each business action (e.g., `DetectionUseCase`) is isolated and testable.
3. **Domain**: Contains the "Source of Truth" for data models and the definition of what a service (like an LLM) must do.
4. **Infrastructure**: Contains the "dirty" details – how to talk to Gemini, how to run a LangGraph, how to configure Presidio.
