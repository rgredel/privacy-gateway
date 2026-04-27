# Data Models & Entities

This document describes the core data structures used in Privacy Gateway, primarily built with Pydantic V2.

## GraphState

The `GraphState` is the central state object passed between nodes in the LangGraph orchestration. It is defined in `src/app/domain/entities.py`.

| Field | Type | Description |
| :--- | :--- | :--- |
| `file_context` | `str` | Input file content used for RAG context. |
| `user_query` | `str` | The original question asked by the user. |
| `raw_pii_strings` | `List[str]` | List of raw strings identified as PII during detection. |
| `labeled_pii_entities` | `List[PIIEntity]` | Structured PII entities with labels and values. |
| `masked_context` | `str` | The context text after pseudonymization. |
| `masked_query` | `str` | The user query after pseudonymization. |
| `vault` | `Dict[str, str]` | A mapping from tokens to original PII values. |
| `is_safe` | `bool` | Whether the request passed the Guardrail security check. |
| `cloud_response` | `str` | The response received from the external cloud LLM. |
| `final_output` | `str` | The decoded final response presented to the user. |
| `error_status` | `str` | Description of any errors encountered. |
| `detection_mode` | `str` | Selected mode: `ner-only`, `llm-only`, or `hybrid`. |

## Core Entities

### PIIEntity

Represents a structured PII entity with its value and label.

```python
class PIIEntity(BaseModel):
    value: str = Field(description="Original PII value")
    label: str = Field(description="Entity label/category")
```

### PIIData

Wrapper for raw PII strings detected by LLM.

```python
class PIIData(BaseModel):
    detected_strings: List[str] = Field(description="List of strings identified as PII")
```

### LabelingData

Wrapper for a list of classified PII entities.

```python
class LabelingData(BaseModel):
    entities: List[PIIEntity] = Field(description="List of classified PII entities")
```

## Infrastructure Configuration

Configurations are managed via `src/app/core/config.py` using Pydantic `BaseSettings`.

- **Local Model:** Default `bielik-1.5b`.
- **Cloud Model:** Default `gemini-2.0-flash`.
- **Security Thresholds:** Sensitivity levels for PromptGuard (default `0.85`).
