import logging
from typing import List, Optional, Any
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, EntityRecognizer, RecognizerResult
from presidio_analyzer.recognizer_registry import RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

# Suppress Presidio and spaCy logs to keep output clean
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

class PolishSpacyRecognizer(EntityRecognizer):
    """
    Custom Presidio recognizer for Polish entities using spaCy models.
    
    This recognizer maps spaCy Polish NER labels (persName, placeName, orgName)
    to standard Presidio entity types (PERSON, LOCATION, ORGANIZATION).
    """

    def __init__(self, nlp_engine: Any):
        """
        Initializes the recognizer with a specific NLP engine.
        
        Args:
            nlp_engine: The NLP engine instance containing the Polish spaCy model.
        """
        super().__init__(
            supported_entities=["PERSON", "LOCATION", "ORGANIZATION"],
            supported_language="pl"
        )
        self.nlp = nlp_engine.nlp["pl"]

    def analyze(self, text: str, entities: List[str], nlp_artifacts: Optional[Any] = None) -> List[RecognizerResult]:
        """
        Analyzes the text for Polish entities using the spaCy model.
        
        Args:
            text: The source text to analyze.
            entities: List of entity types to look for.
            nlp_artifacts: Optional pre-processed NLP artifacts.
            
        Returns:
            A list of RecognizerResult objects containing found entities.
        """
        results = []
        doc = self.nlp(text)
        for ent in doc.ents:
            if ent.label_ == "persName" and "PERSON" in entities:
                results.append(RecognizerResult(entity_type="PERSON", start=ent.start_char, end=ent.end_char, score=0.85))
            elif ent.label_ == "placeName" and "LOCATION" in entities:
                results.append(RecognizerResult(entity_type="LOCATION", start=ent.start_char, end=ent.end_char, score=0.85))
            elif ent.label_ == "orgName" and "ORGANIZATION" in entities:
                results.append(RecognizerResult(entity_type="ORGANIZATION", start=ent.start_char, end=ent.end_char, score=0.85))
        return results

def setup_presidio_analyzer() -> Optional[AnalyzerEngine]:
    """
    Configures the Microsoft Presidio Analyzer with Polish language support and custom recognizers.
    
    This setup includes:
    - Loading the 'pl_core_news_lg' spaCy model.
    - Adding custom regex patterns for Polish-specific identifiers (NIP, REGON, PESEL, IBAN).
    - Integrating the PolishSpacyRecognizer for mapping spaCy entities.
    
    Returns:
        An initialized AnalyzerEngine instance, or None if initialization fails.
    """
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "pl", "model_name": "pl_core_news_lg"}],
    }
    
    try:
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()

        # Define custom regex recognizers for Polish identifiers
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

        registry = RecognizerRegistry()
        registry.supported_languages = ["pl"]
        registry.load_predefined_recognizers(nlp_engine=nlp_engine, languages=["pl"])
        
        # Replace default SpacyRecognizer with our custom Polish version for better mapping
        registry.remove_recognizer("SpacyRecognizer")
        registry.add_recognizer(PolishSpacyRecognizer(nlp_engine))
        
        analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            registry=registry,
            supported_languages=["pl"],
        )
        
        # Register Polish-specific identifier recognizers
        analyzer.registry.add_recognizer(nip_rec)
        analyzer.registry.add_recognizer(regon_rec)
        analyzer.registry.add_recognizer(pesel_rec)
        analyzer.registry.add_recognizer(iban_rec)

        return analyzer
    except Exception as e:
        # Log initialization failure; returning None allows fallback or error handling upstream
        logging.error(f"Presidio initialization failed: {e}")
        return None

def get_pii_candidates(text: str, analyzer: Optional[AnalyzerEngine] = None) -> List[str]:
    """
    Extracts unique PII string candidates from the provided text using Presidio.
    
    Args:
        text: The input string to analyze for PII.
        analyzer: An optional pre-initialized AnalyzerEngine. If None, a new one is created.
        
    Returns:
        A list of unique strings identified as PII candidates.
    """
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
        # Return unique set of candidates
        return list(set(candidates))
    except Exception as e:
        logging.error(f"Presidio analysis failed: {e}")
        return []
