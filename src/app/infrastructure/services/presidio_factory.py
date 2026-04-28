import re
from typing import List, Any
from presidio_analyzer import AnalyzerEngine, RecognizerResult, EntityRecognizer, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from stdnum.pl import pesel, nip, regon

class PolishIdRecognizer(EntityRecognizer):
    """Custom Recognizer for Polish ID Numbers (PESEL, NIP, REGON) with python-stdnum validation."""
    def __init__(self):
        super().__init__(supported_entities=["PL_PESEL", "PL_NIP", "PL_REGON"], supported_language="pl")
        
    def load(self) -> None:
        pass
        
    def analyze(self, text: str, entities: List[str], nlp_artifacts: Any = None) -> List[RecognizerResult]:
        results = []
        
        # PESEL
        if not entities or "PL_PESEL" in entities:
            for match in re.finditer(r'\b\d{11}\b', text):
                if pesel.is_valid(match.group()):
                    results.append(RecognizerResult(entity_type="PL_PESEL", start=match.start(), end=match.end(), score=0.9))
                
        # NIP (various formats)
        if not entities or "PL_NIP" in entities:
            for match in re.finditer(r'\b(?:\d{3}[- ]?\d{3}[- ]?\d{2}[- ]?\d{2}|\d{10})\b', text):
                if nip.is_valid(match.group().replace("-", "").replace(" ", "")):
                    results.append(RecognizerResult(entity_type="PL_NIP", start=match.start(), end=match.end(), score=0.9))
                
        # REGON
        if not entities or "PL_REGON" in entities:
            for match in re.finditer(r'\b(?:\d{9}|\d{14})\b', text):
                if regon.is_valid(match.group()):
                    results.append(RecognizerResult(entity_type="PL_REGON", start=match.start(), end=match.end(), score=0.9))
                
        return results

def setup_presidio_analyzer() -> AnalyzerEngine:
    """
    Konfiguruje i zwraca AnalyzerEngine z obsługą języka polskiego opartą na 
    TransformerSOTA (HerBERT) oraz z rygorystyczną logiką walidacji 
    dla polskich ID (PL_NIP, PL_PESEL, PL_REGON).
    """
    import warnings
    warnings.filterwarnings("ignore", message="Tokenizer does not support real words, using fallback heuristic")
    
    transformer_config = {
        "nlp_engine_name": "transformers",
        "models": [
            {
                "lang_code": "pl",
                "model_name": {
                    "spacy": "pl_core_news_lg", 
                    "transformers": "pczarnik/herbert-base-ner"
                }
            }
        ],
        "ner_model_configuration": {
            "labels_to_ignore": ["O"],
            "aggregation_strategy": "max",
            "stride": 16,
            "alignment_mode": "expand",
            "model_to_presidio_entity_mapping": {
                "PER": "PERSON",
                "LOC": "LOCATION",
                "ORG": "ORGANIZATION"
            }
        }
    }
    
    try:
        provider = NlpEngineProvider(nlp_configuration=transformer_config)
        nlp_engine = provider.create_engine()

        analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine, 
            default_score_threshold=0.4
        )
        
        polish_id_rec = PolishIdRecognizer()
        analyzer.registry.add_recognizer(polish_id_rec)
        
        iban_rec = PatternRecognizer(
            supported_entity="PL_IBAN",
            patterns=[Pattern("IBAN", r"\b[A-Z]{2}\d{2}[ ]?(\d{4}[ ]?){5}\d{4}\b|\b\d{2}[ ]?(\d{4}[ ]?){5}\d{4}\b", 0.85)],
            supported_language="pl",
        )
        analyzer.registry.add_recognizer(iban_rec)
        
        return analyzer
    except Exception as e:
        print(f"[ERROR: PRESIDIO FACTORY] {e}")
        return None
