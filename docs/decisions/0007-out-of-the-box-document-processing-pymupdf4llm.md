# ADR-0007: Out-of-the-box Document Processing with PyMuPDF4LLM

## Status
Accepted

## Context
The previous OCR implementation relied on a complex, manual orchestration of PyMuPDF (for text blocks) and RapidOCR (for image conversion). While functional, this custom code was difficult to maintain and struggled with complex layouts like multi-column invoices and tables. An attempt to integrate IBM's Docling (ADR-0007-alt) failed due to a critical bug in its C++ backend (`docling-parse`) which could not handle Windows file paths containing non-ASCII characters (e.g., "Radosław").

## Decision
We decided to adopt **PyMuPDF4LLM** as the primary document processing engine. It provides a high-level, "out-of-the-box" capability to convert PDFs and images into structured Markdown.

Key reasons for this decision:
1. **Layout-Awareness**: Automatically handles table detection and converts them to Markdown tables, which significantly improves LLM comprehension.
2. **Robustness**: Built on the mature PyMuPDF engine, which is cross-platform and handles non-ASCII Windows paths correctly.
3. **Simplicity**: Reduces the `OCRProcessor` implementation to a few lines of code, adhering to the "Kod jako dokumentacja" principle.
4. **Markdown Native**: Directly outputs the format most preferred by LLMs (Gemini/Bielik) for semantic analysis.

## Consequences
- **Positive**: Drastically reduced complexity in the `utils` layer. Better PII detection recall in documents with tables.
- **Negative**: Adds a dependency on `pymupdf4llm` and its sub-dependencies (`pymupdf_layout`).
- **Technical Debt**: None identified, as it replaces a much larger block of custom code.
