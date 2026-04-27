from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider

def setup_presidio_analyzer() -> AnalyzerEngine:
    """
    Konfiguruje i zwraca AnalyzerEngine z obsługą języka polskiego.
    Dodaje dedykowane rozpoznawacze dla PL_NIP, PL_PESEL i PL_IBAN.
    """
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "pl", "model_name": "pl_core_news_lg"}],
    }
    
    try:
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()

        # 1. Rozpoznawacz NIP
        nip_rec = PatternRecognizer(
            supported_entity="PL_NIP",
            patterns=[Pattern("NIP", r"\b\d{3}[-]?\d{3}[-]?\d{2}[-]?\d{2}\b", 0.85)],
            supported_language="pl",
        )

        # 2. Rozpoznawacz PESEL
        pesel_rec = PatternRecognizer(
            supported_entity="PL_PESEL",
            patterns=[Pattern("PESEL", r"\b\d{11}\b", 0.85)],
            supported_language="pl",
        )

        # 3. Rozpoznawacz IBAN (Konto bankowe)
        iban_rec = PatternRecognizer(
            supported_entity="PL_IBAN",
            patterns=[Pattern("IBAN", r"\b[A-Z]{2}\d{2}[ ]?(\d{4}[ ]?){5}\d{4}\b|\b\d{2}[ ]?(\d{4}[ ]?){5}\d{4}\b", 0.85)],
            supported_language="pl",
        )

        analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine, 
            default_score_threshold=0.4
        )
        
        analyzer.registry.add_recognizer(nip_rec)
        analyzer.registry.add_recognizer(pesel_rec)
        analyzer.registry.add_recognizer(iban_rec)
        
        return analyzer
    except Exception as e:
        print(f"[ERROR: PRESIDIO FACTORY] {e}")
        return None
