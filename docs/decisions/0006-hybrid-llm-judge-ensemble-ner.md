# ADR 0006: Hybrid LLM-as-a-Judge & Ensemble NER Architecture

## Status
Accepted

## Context
Standard NER models (like HerBERT or spaCy) often face a trade-off between Precision and Recall. While HerBERT is highly precise, it might miss complex or inflected PII entities. Conversely, enabling multiple models (Ensemble) increases Recall but significantly degrades Precision due to overlapping false positives. Furthermore, full LLM scanning of all text is cost-prohibitive and poses privacy risks when sending data to the cloud.

## Decision
We implemented a **Hybrid LLM-as-a-Judge** architecture based on the **UDRIL (Uncertainty-DRIven LLM triggering)** principle. Key components:

1.  **Ensemble NER Engine**: We use a combination of HerBERT (Transformers), spaCy (pl_core_news_lg), and deterministic Rules (Regex/Checksums) to maximize initial candidate detection (Recall-oriented).
2.  **Selective Adjudication (UDRIL)**: Instead of scanning everything, the LLM is triggered only for:
    -   Entities with confidence scores in the "Grey Zone" (0.3 - 0.7).
    -   Semantic ambiguities (e.g., LOCATION/ORGANIZATION labels with score < 0.9).
    -   Model Conflicts (e.g., when spaCy finds an entity that HerBERT misses).
3.  **Algorithmic Context Reduction**: To minimize token usage and enhance privacy, the text sent to the LLM is reduced to the minimal sentence fragments containing the candidate PII.
4.  **Semantic Reasoning (Chain-of-Thought)**: The LLM judge is prompted to reason through the identification risk before providing a final "True/False" verdict and optional value correction.

## Consequences
-   **Positive**: Significant increase in Precision (filtering out NER hallucinations). High Recall maintained by the Ensemble engine. Optimized cloud costs and improved privacy.
-   **Negative**: Higher local resource requirements (multiple models in memory). Slightly increased latency for hybrid processing compared to NER-only.
-   **Traceability**:
    -   Core Logic: `src/app/use_cases/detection_use_case.py`
    -   Adjudication: `src/app/infrastructure/llm/langchain_service.py`
    -   Ensemble Config: `src/app/infrastructure/services/presidio_factory.py`
