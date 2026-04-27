# 3. Hybrid PII Detection Engine

**Status:** Accepted

## Context

Detecting Personally Identifiable Information (PII) accurately is the core value proposition of Privacy Gateway. We evaluated two main approaches:
1. **NER-based (Presidio):** Fast, local, reliable for standard formats (emails, phone numbers, Polish PESEL), but lacks semantic context and might miss irregular PII.
2. **LLM-based:** Excellent semantic understanding, can detect PII based on context, but is slower, more expensive, and might produce false positives/hallucinations.

## Decision

We decided to implement a **Hybrid PII Detection Engine**. The system supports three modes:
- **NER-only:** Uses Microsoft Presidio for maximum speed and data privacy.
- **LLM-only:** Uses a local LLM (e.g., Llama 3) for deep semantic analysis.
- **Hybrid (Default):** Runs Presidio first to find high-confidence entities, then uses an LLM to refine findings or find missing context-dependent PII.

Implementation details:
- Standardized `IPrivacyEngine` protocol.
- `DetectionUseCase` coordinates the flow based on user settings.
- Results from both sources are merged and deduplicated before masking.

## Consequences

### Positive
- **High Recall:** Minimizes the risk of leaking PII by combining multiple detection strategies.
- **Flexibility:** Users can choose between speed (NER) and depth (LLM/Hybrid) depending on their needs.
- **Cost/Performance Balance:** LLM is only invoked when high precision is required.

### Negative
- **Merging Complexity:** Requires sophisticated logic to merge overlapping or conflicting PII entities from different sources.
- **Latency:** Hybrid mode is significantly slower than NER-only mode.
