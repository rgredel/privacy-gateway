# 4. Input Security Guardrail (PromptGuard)

**Status:** Accepted

## Context

Privacy Gateway serves as a bridge between users and cloud LLMs. While its primary goal is PII protection, it must also protect against **Prompt Injection** and **Jailbreaking** attempts. Relying solely on the cloud LLM's internal safety filters is insufficient, as some sensitive data might already be leaked to the cloud model during the prompt evaluation phase if the input is malicious.

## Decision

We decided to implement a dedicated **Input Security Guardrail** using a specialized classification model (Meta-Llama-Prompt-Guard).

Key implementation details:
- **Parallel Execution:** The guardrail check runs in parallel with the PII detection/masking flow in LangGraph to minimize latency.
- **Dedicated Use Case:** `GuardrailUseCase` handles the logic, delegating to `ISecurityService`.
- **Sensitivity Threshold:** Users can adjust the sensitivity (0.0 to 1.0) via the UI, allowing for a balance between security and flexibility.
- **Fail-Safe Mechanism:** If the guardrail detects a threat (`is_safe == False`), the request is immediately blocked, and the flow proceeds to a `block_request` node instead of calling the cloud LLM.

## Consequences

### Positive
- **Early Defense:** Attacks are blocked before any data (even pseudonymized) is sent to the cloud model.
- **Performance:** Running in parallel with PII masking ensures that the security check does not add significant overhead to the total response time.
- **User Control:** Runtime configuration allows for fine-tuning based on the specific deployment context.

### Negative
- **False Positives:** High sensitivity might block legitimate user queries that resemble "instruction-like" patterns.
- **Maintenance:** Requires managing an additional model (either local or via an adapter).
