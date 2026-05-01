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

class CustomSpacyRecognizer(EntityRecognizer):
    """Recognizer that runs a dedicated spaCy model to enable true ensembling with Transformers."""
    def __init__(self, nlp: Any = None):
        if nlp:
            self.nlp = nlp
        else:
            import spacy
            self.nlp = spacy.load("pl_core_news_lg")
            
        # Mapowanie etykiet spaCy na standard Presidio
        self.label_map = {
            "persName": "PERSON",
            "geogName": "LOCATION",
            "placeName": "LOCATION",
            "orgName": "ORGANIZATION"
        }
        super().__init__(
            supported_entities=list(set(self.label_map.values())),
            supported_language="pl"
        )
        
    def load(self) -> None:
        pass
        
    def analyze(self, text: str, entities: List[str], nlp_artifacts: Any = None) -> List[RecognizerResult]:
        results = []
        doc = self.nlp(text)
            
        for ent in doc.ents:
            label = self.label_map.get(ent.label_)
            if label and (not entities or label in entities):
                results.append(RecognizerResult(
                    entity_type=label,
                    start=ent.start_char,
                    end=ent.end_char,
                    score=0.55 # Wynik wymuszający adjudykację sędziego LLM
                ))
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
                "ORG": "ORGANIZATION",
                "persName": "PERSON",
                "geogName": "LOCATION",
                "placeName": "LOCATION",
                "orgName": "ORGANIZATION"
            }
        }
    }
    
    try:
        provider = NlpEngineProvider(nlp_configuration=transformer_config)
        nlp_engine = provider.create_engine()
        
        if not nlp_engine:
            print("[ERROR: PRESIDIO FACTORY] nlp_engine is None after creation")
            return None

        analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine, 
            default_score_threshold=0.6
        )
        
        # Dodanie spaCy NER jako drugiego silnika (Ensemble) poprzez CustomSpacyRecognizer
        # Optymalizacja: przekazujemy już załadowany model spaCy z nlp_engine
        # W silniku 'transformers', nlp_engine.nlp jest słownikiem mapującym języki na modele
        spacy_model = getattr(nlp_engine, "nlp", None)
        if isinstance(spacy_model, dict):
            spacy_model = spacy_model.get("pl")
            
        spacy_recognizer = CustomSpacyRecognizer(nlp=spacy_model)
        analyzer.registry.add_recognizer(spacy_recognizer)
        
        polish_id_rec = PolishIdRecognizer()
        analyzer.registry.add_recognizer(polish_id_rec)
        
        # --- Dodatkowe Regex Recognizers ---
        from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer
        
        # E-mail i Telefon (wbudowane w Presidio, ale dodajemy jawnie dla PL)
        analyzer.registry.add_recognizer(EmailRecognizer(supported_language="pl"))
        analyzer.registry.add_recognizer(PhoneRecognizer(supported_language="pl"))

        # Polskie Kody Pocztowe
        zip_code_rec = PatternRecognizer(
            supported_entity="PL_ZIP_CODE",
            patterns=[Pattern("ZipCode", r"\b\d{2}-\d{3}\b", 0.8)],
            supported_language="pl",
        )
        analyzer.registry.add_recognizer(zip_code_rec)

        # Daty (uproszczony wzorzec)
        date_rec = PatternRecognizer(
            supported_entity="DATE_TIME",
            patterns=[Pattern("Date", r"\b\d{2}[./-]\d{2}[./-]\d{4}\b", 0.6)],
            supported_language="pl",
        )
        analyzer.registry.add_recognizer(date_rec)
        
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
