# ADR 0005: Unified SOTA NER Infrastructure

## Status
Accepted

## Context
Previously, the system had multiple implementations of PII detection and masking services:
1. `src/app/infrastructure/pii/`: Contained legacy services using the basic spaCy `pl_core_news_lg` model.
2. `src/app/infrastructure/services/`: Contained production-ready services using the `PresidioFactory` with the **HerBERT** model (SOTA for Polish NER) and rigorous checksum validation (`stdnum`).

This redundancy caused confusion and potential performance/quality degradation if the wrong service was accidentally imported (e.g., in `ner-only` mode or experiments). Specifically, the `ner-only` mode should benefit from the same high-quality local model as the hybrid mode.

## Decision
We decided to:
1. **Remove the legacy `src/app/infrastructure/pii/` directory.**
2. **Unify all PII operations** around the `PresidioFactory` and `PresidioService` located in `src/app/infrastructure/services/`.
3. **Enforce HerBERT** as the default local NER engine across all modes (UI, API, and Experiments) to ensure consistent, high-quality PII detection.
4. **Update Experiment 1 (E1)** to correctly reflect and use this unified infrastructure.

## Consequences
- **Positive:** Single Source of Truth for PII detection configuration. Improved detection quality for `ner-only` mode. Reduced codebase complexity.
- **Negative:** Slightly higher memory usage when running `ner-only` mode compared to a basic spaCy model (HerBERT is a transformer model), but justified by significantly higher precision.
- **Traceability:** Unified configuration is managed in `src/app/infrastructure/services/presidio_factory.py`.
