import re
from typing import List, Any, Optional
from presidio_analyzer import AnalyzerEngine, RecognizerResult, EntityRecognizer, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from stdnum.pl import pesel, nip, regon

class PolishIdRecognizer(EntityRecognizer):
    """Custom Recognizer for Polish ID Numbers (PESEL, NIP, REGON) with python-stdnum validation.
    
    Uses checksum validation to ensure high precision for national identifiers.
    """
    def __init__(self) -> None:
        """Initializes the recognizer for Polish specific entities."""
        super().__init__(supported_entities=["PL_PESEL", "PL_NIP", "PL_REGON"], supported_language="pl")
        
    def load(self) -> None:
        """Required by the interface, no resources to load."""
        pass
        
    def analyze(self, text: str, entities: List[str], nlp_artifacts: Any = None) -> List[RecognizerResult]:
        """Analyzes text for PESEL, NIP, and REGON using regex and checksums.
        
        Args:
            text (str): Input text.
            entities (List[str]): List of entities to look for.
            nlp_artifacts (Any): Optional NLP artifacts.
            
        Returns:
            List[RecognizerResult]: Detected identifiers.
        """
        results = []
        
        # PESEL validation
        if not entities or "PL_PESEL" in entities:
            for match in re.finditer(r'\b\d{11}\b', text):
                if pesel.is_valid(match.group()):
                    results.append(RecognizerResult(entity_type="PL_PESEL", start=match.start(), end=match.end(), score=0.9))
                
        # NIP validation (handles various separators)
        if not entities or "PL_NIP" in entities:
            for match in re.finditer(r'\b(?:\d{3}[- ]?\d{3}[- ]?\d{2}[- ]?\d{2}|\d{10})\b', text):
                if nip.is_valid(match.group().replace("-", "").replace(" ", "")):
                    results.append(RecognizerResult(entity_type="PL_NIP", start=match.start(), end=match.end(), score=0.9))
                
        # REGON validation
        if not entities or "PL_REGON" in entities:
            for match in re.finditer(r'\b(?:\d{9}|\d{14})\b', text):
                if regon.is_valid(match.group()):
                    results.append(RecognizerResult(entity_type="PL_REGON", start=match.start(), end=match.end(), score=0.9))
                
        return results

class CustomSpacyRecognizer(EntityRecognizer):
    """Recognizer that runs a dedicated spaCy model to enable true ensembling with Transformers.
    
    This allows capturing entities that the Transformer model might miss, with lower 
    confidence scores to trigger LLM adjudication.
    """
    def __init__(self, nlp: Any = None) -> None:
        """Initializes with a pre-loaded spaCy model or loads the default one.
        
        Args:
            nlp (Any): Pre-loaded spaCy model.
        """
        if nlp:
            self.nlp = nlp
        else:
            import spacy
            self.nlp = spacy.load("pl_core_news_lg")
            
        # Map spaCy labels to Presidio standard entities
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
        """No additional resources needed."""
        pass
        
    def analyze(self, text: str, entities: List[str], nlp_artifacts: Any = None) -> List[RecognizerResult]:
        """Analyzes text using the internal spaCy model.
        
        Args:
            text (str): Input text.
            entities (List[str]): Requested entity types.
            nlp_artifacts (Any): Optional NLP artifacts.
            
        Returns:
            List[RecognizerResult]: Detected entities.
        """
        results = []
        doc = self.nlp(text)
            
        for ent in doc.ents:
            label = self.label_map.get(ent.label_)
            if label and (not entities or label in entities):
                results.append(RecognizerResult(
                    entity_type=label,
                    start=ent.start_char,
                    end=ent.end_char,
                    score=0.55 # Score set to trigger LLM adjudication in hybrid mode
                ))
        return results

def setup_presidio_analyzer() -> Optional[AnalyzerEngine]:
    """Configures and returns the Presidio AnalyzerEngine for Polish language.
    
    Integrates Transformer-SOTA (HerBERT) as the primary engine and adds 
    custom recognizers for Polish national identifiers and spaCy ensemble.
    
    Returns:
        Optional[AnalyzerEngine]: Fully configured engine or None on failure.
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
        
        # Add spaCy NER as a second ensemble engine via CustomSpacyRecognizer
        # Optimization: Reuse the spaCy model already loaded by the transformers engine
        spacy_model = getattr(nlp_engine, "nlp", None)
        if isinstance(spacy_model, dict):
            spacy_model = spacy_model.get("pl")
            
        spacy_recognizer = CustomSpacyRecognizer(nlp=spacy_model)
        analyzer.registry.add_recognizer(spacy_recognizer)
        
        # Add national identifier recognizers (PESEL, NIP, REGON)
        polish_id_rec = PolishIdRecognizer()
        analyzer.registry.add_recognizer(polish_id_rec)
        
        # --- Predefined and Regex Recognizers ---
        from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer
        
        # Add standard recognizers for Polish language
        analyzer.registry.add_recognizer(EmailRecognizer(supported_language="pl"))
        analyzer.registry.add_recognizer(PhoneRecognizer(supported_language="pl"))

        # Polish Postal Codes (PL_ZIP_CODE)
        zip_code_rec = PatternRecognizer(
            supported_entity="PL_ZIP_CODE",
            patterns=[Pattern("ZipCode", r"\b\d{2}-\d{3}\b", 0.8)],
            supported_language="pl",
        )
        analyzer.registry.add_recognizer(zip_code_rec)

        # Dates (Simplified pattern)
        date_rec = PatternRecognizer(
            supported_entity="DATE_TIME",
            patterns=[Pattern("Date", r"\b\d{2}[./-]\d{2}[./-]\d{4}\b", 0.6)],
            supported_language="pl",
        )
        analyzer.registry.add_recognizer(date_rec)
        
        # Polish Bank Account Numbers (IBAN/NRB)
        iban_rec = PatternRecognizer(
            supported_entity="PL_IBAN",
            patterns=[Pattern("IBAN", r"\b[A-Z]{2}\d{2}[ ]?(\d{4}[ ]?){5}\d{4}\b|\b\d{2}[ ]?(\d{4}[ ]?){5}\d{4}\b", 0.85)],
            supported_language="pl",
        )
        analyzer.registry.add_recognizer(iban_rec)
        
        return analyzer
    except Exception as e:
        print(f"[ERROR: PRESIDIO FACTORY] Failed to setup Presidio: {e}")
        return None
