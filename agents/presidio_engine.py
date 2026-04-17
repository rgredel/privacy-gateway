import logging
from typing import List

# Ukrywamy logi Presidio/spaCy
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

def setup_presidio_analyzer():
    """Konfiguruje Presidio z modelem PL + dodatkowymi rozpoznawaczami polskich identyfikatorów."""
    try:
        from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError:
        return None

    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "pl", "model_name": "pl_core_news_lg"}],
    }
    
    try:
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()

        # Własne rozpoznawacze dla polskich identyfikatorów
        nip_rec = PatternRecognizer(
            supported_entity="PL_NIP",
            patterns=[Pattern("NIP_10", r"\b\d{3}[-]?\d{3}[-]?\d{2}[-]?\d{2}\b", 0.85)],
            supported_language="pl",
        )
        regon_rec = PatternRecognizer(
            supported_entity="PL_REGON",
            patterns=[Pattern("REGON_9", r"\b\d{9}\b", 0.7)],
            supported_language="pl",
        )
        pesel_rec = PatternRecognizer(
            supported_entity="PL_PESEL",
            patterns=[Pattern("PESEL_11", r"\b\d{11}\b", 0.85)],
            supported_language="pl",
        )
        iban_rec = PatternRecognizer(
            supported_entity="PL_IBAN",
            patterns=[Pattern("IBAN_PL", r"\bPL\d{26}\b", 0.9)],
            supported_language="pl",
        )

        analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            supported_languages=["pl"],
        )
        analyzer.registry.add_recognizer(nip_rec)
        analyzer.registry.add_recognizer(regon_rec)
        analyzer.registry.add_recognizer(pesel_rec)
        analyzer.registry.add_recognizer(iban_rec)

        return analyzer
    except Exception as e:
        print(f"[Presidio] Błąd inicjalizacji: {e}")
        return None

def get_pii_candidates(text: str, analyzer=None) -> List[str]:
    """Uruchamia Presidio i zwraca listę unikalnych kandydatów PII."""
    if analyzer is None:
        analyzer = setup_presidio_analyzer()
    
    if analyzer is None:
        return []

    try:
        results = analyzer.analyze(text=text, language="pl")
        candidates = []
        for r in results:
            span = text[r.start:r.end]
            if span.strip():
                candidates.append(span.strip())
        return list(set(candidates))
    except Exception as e:
        print(f"[Presidio] Błąd analizy: {e}")
        return []
